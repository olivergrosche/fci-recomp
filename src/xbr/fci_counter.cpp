// The Halo rifles' displays: the rounds in the magazine and a compass needle drawn into a weapon texture that
// carries the counter marker (fci_counter.h, re/notes/MODELS.md "Counter displays"). The digits are seven
// segments, the compass a ring with a pointer to the north, as on Halo's assault rifle: distance fields give
// them a fill, a bright edge and a glow over the texture's own picture. Only the boxes that changed are drawn
// again; the levels below come from level 0 by a box filter.
#include "fci_counter.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>

extern "C" int fci_counter_state(uint64_t frame, int* rounds, float* heading);   // src/fci_counter.c

namespace fci_counter {

namespace {

constexpr uint8_t kMagic[4] = {'F', 'C', 'I', 'C'}, kEnd[4] = {'C', 'T', 'R', '1'};
constexpr uint32_t kVersion = 1;
constexpr uint32_t kStream = 54;   // marker bytes, three a texel (blue, green, red)
constexpr float kPi = 3.14159265f;

std::atomic<uint64_t> g_recorded{0};   // presents the title recorded

// the segments a to g of each digit
constexpr uint8_t kSegments[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};

struct V2 {
    float x, y;
};

float Clamp01(float v) { return std::min(1.0f, std::max(0.0f, v)); }

// the part of a texel inside the region where d < 0 (d in texels)
float Cover(float d) { return Clamp01(0.5f - d); }

float BoxDistance(V2 p, float x0, float y0, float x1, float y1)
{
    float cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    float qx = std::fabs(p.x - cx) - (x1 - x0) / 2, qy = std::fabs(p.y - cy) - (y1 - y0) / 2;
    float ox = std::max(qx, 0.0f), oy = std::max(qy, 0.0f);
    return std::sqrt(ox * ox + oy * oy) + std::min(std::max(qx, qy), 0.0f);
}

// signed distance to a polygon (its points in order)
float PolygonDistance(V2 p, const V2* v, int n)
{
    float d = (p.x - v[0].x) * (p.x - v[0].x) + (p.y - v[0].y) * (p.y - v[0].y);
    float s = 1;
    for (int i = 0, j = n - 1; i < n; j = i, i++) {
        V2 e{v[j].x - v[i].x, v[j].y - v[i].y}, w{p.x - v[i].x, p.y - v[i].y};
        float t = Clamp01((w.x * e.x + w.y * e.y) / std::max(e.x * e.x + e.y * e.y, 1e-9f));
        V2 b{w.x - e.x * t, w.y - e.y * t};
        d = std::min(d, b.x * b.x + b.y * b.y);
        bool c1 = p.y >= v[i].y, c2 = p.y<v[j].y, c3 = e.x * w.y> e.y * w.x;
        if ((c1 && c2 && c3) || (!c1 && !c2 && !c3))
            s = -s;
    }
    return s * std::sqrt(d);
}

void Read3(const uint8_t* s, float* out)
{
    for (int i = 0; i < 3; i++)
        out[i] = s[i];
}

Box ReadBox(const uint8_t* s, uint32_t w, uint32_t h)
{
    uint16_t v[4];
    std::memcpy(v, s, sizeof v);
    Box b{std::min<int>(v[0], int(w)), std::min<int>(v[1], int(h)), std::min<int>(v[2], int(w)),
          std::min<int>(v[3], int(h))};
    return b;
}

// a box's texels drawn by shade(texel centre, colour in out): from the picture under it
template <typename Shade> void DrawBox(Display& d, const Box& b, Shade shade)
{
    for (int y = std::max(b.y0, 1); y < b.y1; y++) {
        for (int x = b.x0; x < b.x1; x++) {
            size_t at = (size_t(y) * d.w + x) * 4;
            float c[3] = {d.base[at + 2], d.base[at + 1], d.base[at]};   // red, green, blue
            shade(V2{x + 0.5f, y + 0.5f}, c);
            d.now[at] = uint8_t(std::lround(std::min(255.0f, c[2])));
            d.now[at + 1] = uint8_t(std::lround(std::min(255.0f, c[1])));
            d.now[at + 2] = uint8_t(std::lround(std::min(255.0f, c[0])));
        }
    }
}

void Mix(float* c, const float* to, float a)
{
    for (int i = 0; i < 3; i++)
        c[i] += (to[i] - c[i]) * a;
}

// the glow, the fill inside, the bright edge along the outline, by the distance to the shape
void Paint(const Layout& l, float dist, const float* fill, const float* edge, float* c)
{
    float glow = l.glow_strength * std::exp(-std::max(dist, 0.0f) / std::max(l.glow_reach, 0.25f));
    for (int i = 0; i < 3; i++)
        c[i] += l.glow[i] * glow;
    Mix(c, fill, Cover(dist + l.edge_width / 2));
    Mix(c, edge, Cover(std::fabs(dist) - l.edge_width / 2));
}

void DrawDigit(Display& d, const Box& b, int digit)
{
    const Layout& l = d.layout;
    float in = l.edge_width / 2 + 0.5f;   // the edge stays in the box
    float x0 = b.x0 + in, y0 = b.y0 + in, x1 = b.x1 - in, y1 = b.y1 - in;
    float w = x1 - x0, h = y1 - y0, t = std::max(1.0f, l.thickness * w), g = l.gap * w, my = y0 + h / 2;
    struct Seg {
        float x0, y0, x1, y1;
    } seg[7] = {
            {x0 + g, y0, x1 - g, y0 + t},               // a
            {x1 - t, y0 + g, x1, my + t / 2 - g},       // b
            {x1 - t, my - t / 2 + g, x1, y1 - g},       // c
            {x0 + g, y1 - t, x1 - g, y1},               // d
            {x0, my - t / 2 + g, x0 + t, y1 - g},       // e
            {x0, y0 + g, x0 + t, my + t / 2 - g},       // f
            {x0 + g, my - t / 2, x1 - g, my + t / 2},   // g
    };
    uint8_t on = digit >= 0 && digit <= 9 ? kSegments[digit] : 0;
    DrawBox(d, b, [&](V2 p, float* c) {
        if (!on)
            return;
        float dist = 1e9f;
        for (int s = 0; s < 7; s++)
            if (on >> s & 1)
                dist = std::min(dist, BoxDistance(p, seg[s].x0, seg[s].y0, seg[s].x1, seg[s].y1));
        Paint(l, dist, l.fill, l.edge, c);
    });
}

// a ring and a pointer from it to the edge of the box, turned by angle (radians, clockwise from up)
void DrawCompass(Display& d, float angle)
{
    const Layout& l = d.layout;
    const Box& b = l.compass;
    V2 c{(b.x0 + b.x1) / 2.0f, (b.y0 + b.y1) / 2.0f};
    float half = std::min(b.x1 - b.x0, b.y1 - b.y0) / 2.0f - l.edge_width / 2 - 0.5f;
    float r = 0.52f * half;
    V2 dir{std::sin(angle), -std::cos(angle)}, side{-dir.y, dir.x};
    auto at = [&](float along, float across) {
        return V2{c.x + dir.x * along + side.x * across, c.y + dir.y * along + side.y * across};
    };
    // the pointer: Halo's drop, a kite from inside the ring out past it
    V2 kite[4] = {at(half, 0), at(0.55f * r, 0.62f * r), at(0.1f * r, 0), at(0.55f * r, -0.62f * r)};
    DrawBox(d, b, [&](V2 p, float* col) {
        float ring = std::fabs(std::hypot(p.x - c.x, p.y - c.y) - r);
        float k = PolygonDistance(p, kite, 4);
        float glow = l.glow_strength
                     * std::exp(-std::max(std::min(ring, k), 0.0f) / std::max(l.glow_reach, 0.25f));
        for (int i = 0; i < 3; i++)
            col[i] += l.glow[i] * glow;
        Mix(col, l.compass_edge, Cover(ring - l.edge_width / 2));
        Mix(col, l.compass_fill, Cover(k + l.edge_width / 2));
        Mix(col, l.compass_edge, Cover(std::fabs(k) - l.edge_width / 2));
    });
}

void Restore(Display& d, const Box& b)
{
    for (int y = b.y0; y < b.y1; y++) {
        size_t at = (size_t(y) * d.w + b.x0) * 4;
        std::memcpy(&d.now[at], &d.base[at], size_t(b.x1 - b.x0) * 4);
    }
}

// level 0 and the box filtered levels below it
void Levels(const Display& d, uint32_t levels, std::vector<std::vector<uint8_t>>& out)
{
    out.assign(std::max(levels, 1u), {});
    out[0] = d.now;
    uint32_t w = d.w, h = d.h;
    for (uint32_t l = 1; l < out.size(); l++) {
        uint32_t nw = std::max(w / 2, 1u), nh = std::max(h / 2, 1u);
        const std::vector<uint8_t>& src = out[l - 1];
        std::vector<uint8_t>& dst = out[l];
        dst.resize(size_t(nw) * nh * 4);
        for (uint32_t y = 0; y < nh; y++)
            for (uint32_t x = 0; x < nw; x++)
                for (uint32_t k = 0; k < 4; k++) {
                    uint32_t xa = std::min(2 * x, w - 1), xb = std::min(2 * x + 1, w - 1);
                    uint32_t ya = std::min(2 * y, h - 1), yb = std::min(2 * y + 1, h - 1);
                    uint32_t s = src[(size_t(ya) * w + xa) * 4 + k] + src[(size_t(ya) * w + xb) * 4 + k]
                                 + src[(size_t(yb) * w + xa) * 4 + k] + src[(size_t(yb) * w + xb) * 4 + k];
                    dst[(size_t(y) * nw + x) * 4 + k] = uint8_t((s + 2) / 4);
                }
        w = nw;
        h = nh;
    }
}

}   // namespace

std::shared_ptr<Display> Detect(const uint8_t* px, uint32_t w, uint32_t h, uint32_t pitch)
{
    if (w * 3 < kStream || h < 4 || px[0] != kMagic[0] || px[1] != kMagic[1] || px[2] != kMagic[2])
        return nullptr;
    uint8_t s[kStream];
    for (uint32_t i = 0; i < kStream; i++)
        s[i] = px[(i / 3) * 4 + i % 3];
    if (std::memcmp(s, kMagic, 4) || s[4] != kVersion || std::memcmp(s + 50, kEnd, 4))
        return nullptr;
    auto d = std::make_shared<Display>();
    Layout& l = d->layout;
    l.has_compass = s[5] & 1;
    l.digits = s[5] & 2;
    l.digit[0] = ReadBox(s + 6, w, h);
    l.digit[1] = ReadBox(s + 14, w, h);
    l.compass = ReadBox(s + 22, w, h);
    Read3(s + 30, l.fill);
    Read3(s + 33, l.edge);
    Read3(s + 36, l.compass_edge);
    Read3(s + 39, l.compass_fill);
    Read3(s + 42, l.glow);
    l.glow_strength = s[45] / 255.0f;
    l.edge_width = s[46] / 16.0f;
    l.glow_reach = s[47] / 4.0f;
    l.thickness = s[48] / 255.0f;
    l.gap = s[49] / 255.0f;
    d->w = w;
    d->h = h;
    d->base.resize(size_t(w) * h * 4);
    for (uint32_t y = 0; y < h; y++)
        std::memcpy(&d->base[size_t(y) * w * 4], px + size_t(y) * pitch, size_t(w) * 4);
    std::memcpy(&d->base[0], &d->base[size_t(w) * 4], size_t(w) * 4);   // the marker's row: the one below
    d->now = d->base;
    return d;
}

bool Update(Display& d, uint64_t frame, uint32_t levels, std::vector<std::vector<uint8_t>>& out)
{
    if (d.frame == frame)
        return false;
    d.frame = frame;
    int rounds = -1;
    float heading = 0;
    bool north = fci_counter_state(frame, &rounds, &heading) & 1;
    rounds = std::min(rounds, 99);
    // the needle points north: against the heading, in tenths of a degree
    int needle = (int(std::lround((north ? -heading : 0.0f) * 10)) % 3600 + 3600) % 3600;
    bool changed = d.rounds == -2;
    const Layout& l = d.layout;
    if (l.digits && rounds != d.rounds) {
        for (int i = 0; i < 2; i++) {
            Restore(d, l.digit[i]);
            if (rounds >= 0)
                DrawDigit(d, l.digit[i], i ? rounds % 10 : rounds / 10);
        }
        changed = true;
    }
    d.rounds = rounds;
    if (l.has_compass && !l.compass.Empty() && needle != d.needle) {
        Restore(d, l.compass);
        DrawCompass(d, needle / 10.0f * kPi / 180);
        d.needle = needle;
        changed = true;
    }
    if (changed)
        Levels(d, levels, out);
    return changed;
}

void NotePresent() { g_recorded.fetch_add(1, std::memory_order_release); }

}   // namespace fci_counter

// the frame the title is recording: the game code's tag for what it publishes (src/fci_counter.c)
extern "C" uint64_t fci_counter_frame(void)
{ return fci_counter::g_recorded.load(std::memory_order_acquire); }
