#pragma once
// The Halo rifles' displays (re/notes/MODELS.md "Counter displays"): a weapon texture that carries a marker in
// row 0 (tools/weapon_import.py, "counter") is drawn over on the host with the rounds in the magazine and a
// compass needle, from what the game code publishes (src/fci_counter.c). The renderer asks Detect when it
// decodes a texture's level 0 for upload and Update when it binds one that had the marker.
#include <cstdint>
#include <memory>
#include <vector>

namespace fci_counter {

struct Box {
    int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    bool Empty() const { return x1 <= x0 || y1 <= y0; }
};

struct Layout {
    Box digit[2];   // the tens and the ones
    Box compass;
    bool digits = false, has_compass = false;
    float fill[3], edge[3], compass_edge[3], compass_fill[3], glow[3];
    float glow_strength = 0, edge_width = 1.5f, glow_reach = 3, thickness = 0.2f, gap = 0;
};

// a counter texture: its picture without the marker, and what it shows now
struct Display {
    Layout layout;
    uint32_t w = 0, h = 0;
    std::vector<uint8_t> base;   // level 0, BGRA rows of w * 4 bytes
    std::vector<uint8_t> now;    // level 0 as last drawn
    int rounds = -2;             // shown: -1 none, -2 not drawn yet
    int needle = -1;             // shown: the needle's angle in tenths of a degree, -1 not drawn yet
    uint64_t frame = ~0ull;      // the frame the state was last read for
};

// a texture's level 0 as decoded for upload (BGRA rows of pitch bytes): its display when row 0 holds the marker
std::shared_ptr<Display> Detect(const uint8_t* px, uint32_t w, uint32_t h, uint32_t pitch);

// once a frame: the game's state for frame (the renderer's present count while it draws it); true when the
// picture changed, with every level of it in out (BGRA rows, tightly packed, largest first, levels of them)
bool Update(Display& d, uint64_t frame, uint32_t levels, std::vector<std::vector<uint8_t>>& out);

// the title recorded a present (the render thread, gpu/render_thread.cpp): the game code tags what it publishes
// with the count (fci_counter_frame), and the renderer, a frame behind, reads the state of the frame it draws
void NotePresent();

}   // namespace fci_counter
