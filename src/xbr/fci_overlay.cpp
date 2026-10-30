// FCI: the mod menu, a Dear ImGui overlay over the game (src/fci_mods.c holds the mods). F1 or both sticks
// pressed together open and close it; while it is open the game gets no input (a neutral pad, no keys, no
// mouse) and the menu takes the keyboard, the mouse and the controller. A choice is saved at once and takes
// effect when the game next opens its archives (a level change, the main menu: a new instance).
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <iterator>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include <imgui.h>
#include <imgui_internal.h>   // SetFocusID: the public focus calls leave a just opened window without one
#include <backends/imgui_impl_win32.h>

#include "app/app.h"
#include "../fci_mods.h"

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND hWnd, UINT msg, WPARAM wParam,
                                                             LPARAM lParam);

extern "C" {
void fci_input_release_all(void);   // fci_input.c
}

namespace {

constexpr uint8_t kThumbs = 0x40 | 0x80;   // the pad report's digital byte: both stick clicks
constexpr float kFontPixels = 36.0f;

std::atomic<bool> g_open{false};
std::atomic<int> g_focus{
        0};   // frames left in which the first mod asks for the focus (a window's first drops it)
std::atomic<bool> g_hold{false};   // the game sees a neutral pad until every button is let go
HWND g_hwnd = nullptr;
bool g_ready = false;

void SetOpen(bool on)
{
    if (g_open.exchange(on) == on)
        return;
    g_hold = true;
    g_focus = on ? 3 : 0;
    fci_input_release_all();
    if (g_ready) {
        std::lock_guard lock(app::UiLock());
        ImGui::GetIO().MouseDrawCursor = on;
    }
}

bool Pressed(const uint8_t* r)
{
    if (r[2] & 0x3F)
        return true;
    for (int i = 4; i < 12; i++)
        if (r[i] > 0x20)
            return true;
    for (int i = 12; i < 20; i += 2) {
        int16_t v = int16_t(r[i] | r[i + 1] << 8);
        if (v > 8000 || v < -8000)
            return true;
    }
    return (r[2] & kThumbs) != 0;
}

const char* State(int i)
{
    bool on = fci_mods_enabled(i), active = fci_mods_active(i);
    if (on && active)
        return "active";
    if (on)
        return "on from the next load";
    if (active)
        return "off from the next load";
    return "";
}

void DrawMenu()
{
    ImGuiIO& io = ImGui::GetIO();
    ImVec2 size(std::min(io.DisplaySize.x * 0.9f, std::max(io.DisplaySize.y * 1.1f, 640.0f)),
                io.DisplaySize.y * 0.8f);
    ImGui::SetNextWindowSize(size, ImGuiCond_Always);
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Always,
                            ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowFocus();
    bool open = true;
    if (!ImGui::Begin("Mods", &open,
                      ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings
                              | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove)) {
        ImGui::End();
        return;
    }
    if (!open)
        SetOpen(false);
    int n = fci_mods_count();
    ImGui::TextDisabled("A choice takes effect at the next level change or after Quit to Main Menu.");
    if (fci_mods_pending())
        ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.3f, 1.0f),
                           "Changed: load a level or go to the main menu to see it.");
    ImGui::Separator();
    if (!n) {
        ImGui::TextWrapped("No mods found in %s", fci_mods_folder());
    } else {
        std::vector<std::string> groups;
        for (int i = 0; i < n; i++)
            if (std::find(groups.begin(), groups.end(), fci_mods_group(i)) == groups.end())
                groups.push_back(fci_mods_group(i));
        std::sort(groups.begin(), groups.end(), [](const std::string& a, const std::string& b) {
            return a.empty() != b.empty() ? !a.empty() : a < b;   // the ungrouped last
        });
        bool ask = g_focus > 0;   // for the first mod only
        if (ask)
            g_focus--;
        for (const std::string& g : groups) {
            ImGui::SeparatorText(g.empty() ? "Other" : g.c_str());
            for (int i = 0; i < n; i++) {
                if (g != fci_mods_group(i))
                    continue;
                ImGui::PushID(i);
                bool on = fci_mods_enabled(i), focus = ask;
                ask = false;
                if (ImGui::Checkbox(fci_mods_name(i), &on))
                    fci_mods_set(i, on);
                if (focus) {   // the controller's first press acts on the first mod
                    ImGui::SetFocusID(ImGui::GetItemID(), ImGui::GetCurrentWindow());
                    ImGui::GetCurrentContext()->NavCursorVisible = true;
                }
                if (*State(i)) {
                    ImGui::SameLine();
                    ImGui::TextDisabled("(%s)", State(i));
                }
                ImGui::Indent();
                if (*fci_mods_description(i))
                    ImGui::TextWrapped("%s", fci_mods_description(i));
                std::string others;
                for (int j = 0; j < n; j++)
                    if (fci_mods_conflict(i, j))
                        others += (others.empty() ? "" : ", ") + std::string(fci_mods_name(j));
                if (!others.empty())
                    ImGui::TextDisabled("Replaces the same files as %s: one of them at a time.",
                                        others.c_str());
                if (*fci_mods_credit(i))
                    ImGui::TextDisabled("%s", fci_mods_credit(i));
                ImGui::Unindent();
                ImGui::Spacing();
                ImGui::PopID();
            }
        }
    }
    ImGui::Separator();
    if (ImGui::Button("Close"))
        SetOpen(false);
    ImGui::SameLine();
    ImGui::TextDisabled("F1 or both sticks pressed: open and close");
    ImGui::End();
}

}   // namespace

// The renderer's Init (gpu/d3d12.cpp), before the Direct3D 12 backend: the context, the font, the window
void fci_overlay_init(HWND hwnd)
{
    std::lock_guard lock(app::UiLock());
    g_hwnd = hwnd;
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.LogFilename = nullptr;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad;   // from the pad reports (fci_overlay_pad)
    io.ConfigNavCursorVisibleAlways = true;   // a controller's first press acts instead of showing the cursor
    char fonts[MAX_PATH];
    UINT n = GetWindowsDirectoryA(fonts, MAX_PATH);
    std::string path = std::string(fonts, n) + "\\Fonts\\segoeui.ttf";
    if (GetFileAttributesA(path.c_str()) == INVALID_FILE_ATTRIBUTES
        || !io.Fonts->AddFontFromFileTTF(path.c_str(), kFontPixels)) {
        ImFontConfig c;
        c.SizePixels = kFontPixels;
        io.Fonts->AddFontDefault(&c);
    }
    ImGui::StyleColorsDark();
    ImGuiStyle& s = ImGui::GetStyle();
    s.WindowRounding = 6.0f;
    s.FrameRounding = 4.0f;
    s.Colors[ImGuiCol_WindowBg].w = 0.92f;
    s.ScaleAllSizes(1.5f);
    ImGui_ImplWin32_Init(hwnd);
    g_ready = true;
}

// app::kGame.ui, each frame from the renderer with app::UiLock held
void fci_overlay_draw(double)
{
    ImGuiIO& io = ImGui::GetIO();
    io.FontGlobalScale = std::clamp(io.DisplaySize.y / 1500.0f, 0.4f, 1.2f);   // 36 px fonts at 1080p: 26
    if (g_open)
        DrawMenu();
}

// The game window's messages (fci_xbr_glue.cpp), first: true when the menu took the message
bool fci_overlay_message(HWND w, UINT msg, WPARAM wp, LPARAM lp, LRESULT* result)
{
    if (!g_ready)
        return false;
    if (msg == WM_KEYDOWN && wp == VK_F1 && !(lp & (1 << 30))) {
        SetOpen(!g_open);
        *result = 0;
        return true;
    }
    if (!g_open)
        return false;
    if (msg == WM_KEYDOWN && wp == VK_ESCAPE) {
        SetOpen(false);
        *result = 0;
        return true;
    }
    {
        std::lock_guard lock(app::UiLock());
        if (LRESULT r = ImGui_ImplWin32_WndProcHandler(w, msg, wp, lp)) {
            *result = r;
            return true;
        }
    }
    switch (msg) {   // the game's input stays with the menu
    case WM_KEYDOWN:
    case WM_KEYUP:
    case WM_CHAR:
    case WM_INPUT:
    case WM_MOUSEMOVE:
    case WM_LBUTTONDOWN:
    case WM_LBUTTONUP:
    case WM_RBUTTONDOWN:
    case WM_RBUTTONUP:
    case WM_MBUTTONDOWN:
    case WM_MBUTTONUP:
    case WM_XBUTTONDOWN:
    case WM_XBUTTONUP:
    case WM_MOUSEWHEEL:
        if (msg == WM_INPUT)
            return false;   // DefWindowProc cleans up raw input; the game's handler checks fci_overlay_open
        *result = 0;
        return true;
    case WM_SETCURSOR:
        SetCursor(nullptr);   // the menu draws its own
        *result = TRUE;
        return true;
    }
    return false;
}

extern "C" int fci_overlay_open(void) { return g_open; }

namespace {
// the pad report as the menu's controller: what the game would have got (a real pad, the keyboard and mouse
// bindings, a test script), so the menu answers to all of them; imconfig.h keeps the backend off XInput
struct PadKey {
    ImGuiKey key;
    int byte;       // in the report
    uint8_t mask;   // a digital button; 0 for an analog one (pressed past a quarter)
};
constexpr PadKey kPadKeys[] = {
        {ImGuiKey_GamepadDpadUp, 2, 0x01},   {ImGuiKey_GamepadDpadDown, 2, 0x02},
        {ImGuiKey_GamepadDpadLeft, 2, 0x04}, {ImGuiKey_GamepadDpadRight, 2, 0x08},
        {ImGuiKey_GamepadStart, 2, 0x10},    {ImGuiKey_GamepadBack, 2, 0x20},
        {ImGuiKey_GamepadFaceDown, 4, 0},    {ImGuiKey_GamepadFaceLeft, 6, 0},
        {ImGuiKey_GamepadFaceUp, 7, 0},
};

void PadToMenu(const uint8_t* r, bool on)
{
    static bool sent[std::size(kPadKeys)];
    static float stick[4];   // left stick: left, right, up, down
    std::lock_guard lock(app::UiLock());
    ImGuiIO& io = ImGui::GetIO();
    for (size_t i = 0; i < std::size(kPadKeys); i++) {
        const PadKey& k = kPadKeys[i];
        bool down = on && (k.mask ? (r[k.byte] & k.mask) != 0 : r[k.byte] > 0x40);
        if (down != sent[i])
            io.AddKeyEvent(k.key, sent[i] = down);
    }
    float x = int16_t(r[12] | r[13] << 8) / 32767.0f, y = int16_t(r[14] | r[15] << 8) / 32767.0f;
    const float v[4] = {std::max(0.0f, -x), std::max(0.0f, x), std::max(0.0f, y), std::max(0.0f, -y)};
    const ImGuiKey keys[4] = {ImGuiKey_GamepadLStickLeft, ImGuiKey_GamepadLStickRight,
                              ImGuiKey_GamepadLStickUp, ImGuiKey_GamepadLStickDown};
    for (int i = 0; i < 4; i++) {
        float a = on && v[i] > 0.25f ? std::min(1.0f, (v[i] - 0.25f) / 0.75f) : 0.0f;
        if (a != stick[i])
            io.AddKeyAnalogEvent(keys[i], a > 0.1f, stick[i] = a);
    }
}
}   // namespace

// Each finished pad report before the game reads it (fci_record.c): both sticks pressed toggle the menu,
// B closes it, the rest steers it; the game sees a neutral pad while the menu is open and until the
// buttons are let go after it
extern "C" void fci_overlay_pad(int pad, uint8_t* report)
{
    static bool chord[4], b_down[4], steering;
    if (pad < 0 || pad >= 4 || !g_ready)
        return;
    bool both = (report[2] & kThumbs) == kThumbs;
    if (both && !chord[pad])
        SetOpen(!g_open);
    chord[pad] = both;
    bool b = report[5] > 0x40;
    if (g_open && b && !b_down[pad])
        SetOpen(false);
    b_down[pad] = b;
    if (pad == 0 && (g_open || steering)) {
        PadToMenu(report, g_open && !both);
        steering = g_open;
    }
    if (!g_open && g_hold && !Pressed(report))
        g_hold = false;
    if (g_open || g_hold)
        std::memset(report + 2, 0, 18);
}
