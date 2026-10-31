// FCI: the mod menu, a Dear ImGui overlay over the game (src/fci_mods.c holds the mods). F1 or Insert (fci.ini
// mods-menu-key) or a controller's both sticks pressed together open and close it, and the MODS entries of the
// main menu and the pause menus open it (src/fci_mainmenu.c); while it is open the game gets no input (a neutral pad, no keys, no
// mouse) and the menu takes the keyboard, the mouse and the controller. A choice is saved at once and takes
// effect when the game next opens its archives (a level change, the main menu: a new instance). The settings
// at the top (weapon strength, enemy damage: fci_damage.c) take effect at once, with no mods too.
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <iterator>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
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
void fci_input_release_all(void);           // fci_input.c
int fci_input_key_code(const char* name);   // fci_input.c: F1, INSERT, ... as in the bindings
int fci_input_stick_click_held(void);       // fci_input.c: a key bound to a stick click is held
}

namespace {

constexpr uint8_t kThumbs = 0x40 | 0x80;   // the pad report's digital byte: both stick clicks
// the keys that open and close the menu: fci.ini mods-menu-key (RECOMP_FCI_MODS_KEY), names as in the
// bindings. Insert besides F1: a browser in front of a remote desktop keeps F1 (its help) for itself.
constexpr const char* kDefaultKeys = "F1,INSERT";
constexpr float kFontPixels = 36.0f;

std::atomic<bool> g_open{false};
std::atomic<int> g_focus{
        0};   // frames left in which the first setting asks for the focus (a window's first drops it)
std::atomic<bool> g_hold{false};   // the game sees a neutral pad until every button is let go
// the menu follows the controller once its buttons are let go after opening: the A that chose the main
// menu's MODS entry is still down then and would switch the first mod
std::atomic<bool> g_steer_wait{false};
HWND g_hwnd = nullptr;
bool g_ready = false;
std::vector<int> g_keys;                     // virtual keys
std::vector<std::string> g_key_names_each;   // the same keys' names, for the log
std::string g_key_names;                     // for the menu's hint: "F1 or INSERT"

void ReadKeys()
{
    const char* e = std::getenv("RECOMP_FCI_MODS_KEY");
    std::string list = e && *e ? e : kDefaultKeys;
    size_t at = 0;
    while (at <= list.size()) {
        size_t end = list.find(',', at);
        std::string name = list.substr(at, end == std::string::npos ? std::string::npos : end - at);
        name.erase(0, name.find_first_not_of(" \t"));
        name.erase(name.find_last_not_of(" \t") + 1);
        int vk = name.empty() ? -1 : fci_input_key_code(name.c_str());
        if (vk > 0) {
            g_keys.push_back(vk);
            g_key_names_each.push_back("key " + name);
            g_key_names += (g_key_names.empty() ? "" : " or ") + name;
        }
        if (end == std::string::npos)
            break;
        at = end + 1;
    }
}

void SetOpen(bool on, const char* by)
{
    if (g_open.exchange(on) == on)
        return;
    std::fprintf(stderr, "[FCI] mod menu %s (%s)\n", on ? "opened" : "closed", by);
    g_hold = true;
    g_steer_wait = on;
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

// a dimmed line that wraps at the window's edge (TextDisabled does not)
void DimWrapped(const char* text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyle().Colors[ImGuiCol_TextDisabled]);
    ImGui::TextWrapped("%s", text);
    ImGui::PopStyleColor();
}

// a percent slider in steps of FCI_STRENGTH_STEP: the mouse drags it, and the keyboard's arrows, the pad's
// d-pad and left stick move it a step while it has the focus (ImGui itself only once it is activated, and
// then one of its steps is one of ours). True when it changed.
bool StepSlider(const char* label, int* percent, bool focus)
{
    int step = *percent / FCI_STRENGTH_STEP;
    char shown[32];
    std::snprintf(shown, sizeof shown, "%d %%%%", *percent);   // a format without a conversion: the text
    bool changed = ImGui::SliderInt(label, &step, FCI_STRENGTH_MIN / FCI_STRENGTH_STEP,
                                    FCI_STRENGTH_MAX / FCI_STRENGTH_STEP, shown,
                                    ImGuiSliderFlags_NoInput | ImGuiSliderFlags_AlwaysClamp);
    if (focus) {   // the controller's first press acts here
        ImGui::SetFocusID(ImGui::GetItemID(), ImGui::GetCurrentWindow());
        ImGui::GetCurrentContext()->NavCursorVisible = true;
    }
    if (ImGui::IsItemFocused() && !ImGui::IsItemActive()) {
        int move = 0;
        for (ImGuiKey k : {ImGuiKey_LeftArrow, ImGuiKey_GamepadDpadLeft, ImGuiKey_GamepadLStickLeft})
            move -= ImGui::IsKeyPressed(k, true);
        for (ImGuiKey k : {ImGuiKey_RightArrow, ImGuiKey_GamepadDpadRight, ImGuiKey_GamepadLStickRight})
            move += ImGui::IsKeyPressed(k, true);
        if (move) {
            step = std::clamp(step + move, FCI_STRENGTH_MIN / FCI_STRENGTH_STEP,
                              FCI_STRENGTH_MAX / FCI_STRENGTH_STEP);
            changed = true;
        }
    }
    if (changed)
        *percent = step * FCI_STRENGTH_STEP;
    return changed;
}

// the settings above the mods: in effect at once, saved in mods\settings.ini (fci_mods.c)
void DrawSettings(bool focus)
{
    ImGui::SeparatorText("Settings");
    int weapon = fci_mods_weapon_strength(), enemy = fci_mods_enemy_damage();
    ImGui::PushItemWidth(ImGui::GetContentRegionAvail().x * 0.45f);
    bool changed = StepSlider("Weapon strength", &weapon, focus);
    ImGui::Indent();
    DimWrapped("The damage your weapons deal to people and creatures: bullets, melee and your explosions.");
    ImGui::Unindent();
    changed |= StepSlider("Enemy damage", &enemy, false);
    ImGui::Indent();
    DimWrapped("The damage others deal to you. Both take effect at once.");
    ImGui::Unindent();
    ImGui::PopItemWidth();
    if (changed)
        fci_mods_set_strengths(weapon, enemy);
    ImGui::Spacing();
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
        SetOpen(false, "the window's X");
    bool ask = g_focus > 0;   // the first setting asks for the focus (a window's first frames drop it)
    if (ask)
        g_focus--;
    DrawSettings(ask);
    int n = fci_mods_count();
    ImGui::SeparatorText("Mods");
    ImGui::TextDisabled("A choice takes effect at the next level change or after Quit to Main Menu.");
    if (fci_mods_pending())
        ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.3f, 1.0f),
                           "Changed: load a level or go to the main menu to see it.");
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
        for (const std::string& g : groups) {
            ImGui::SeparatorText(g.empty() ? "Other" : g.c_str());
            for (int i = 0; i < n; i++) {
                if (g != fci_mods_group(i))
                    continue;
                ImGui::PushID(i);
                bool on = fci_mods_enabled(i);
                if (ImGui::Checkbox(fci_mods_name(i), &on))
                    fci_mods_set(i, on);
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
                    DimWrapped(("Replaces the same files as " + others + ": one of them at a time.").c_str());
                if (*fci_mods_credit(i))
                    DimWrapped(fci_mods_credit(i));
                ImGui::Unindent();
                ImGui::Spacing();
                ImGui::PopID();
            }
        }
    }
    ImGui::Separator();
    if (ImGui::Button("Close"))
        SetOpen(false, "Close");
    ImGui::SameLine();
    ImGui::TextDisabled("%s%sboth sticks pressed: open and close", g_key_names.c_str(),
                        g_keys.empty() ? "" : " or ");
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
    ReadKeys();
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
    // a menu key toggles once per press: its own down state, not the message's repeat bit, which a
    // remote desktop's injected keys need not carry
    static int held = 0;
    auto key = std::find(g_keys.begin(), g_keys.end(), int(wp));
    if (key != g_keys.end() && (msg == WM_KEYDOWN || msg == WM_KEYUP)) {
        if (msg == WM_KEYDOWN && held != int(wp)) {
            // the name, and whether Windows saw the key down already (a remote desktop's repeats)
            std::string by = g_key_names_each[key - g_keys.begin()] + (lp & (1 << 30) ? ", repeat" : "");
            SetOpen(!g_open, by.c_str());
        }
        held = msg == WM_KEYDOWN ? int(wp) : 0;
        *result = 0;
        return true;
    }
    if (msg == WM_KILLFOCUS)
        held = 0;
    if (!g_open)
        return false;
    if (msg == WM_KEYDOWN && wp == VK_ESCAPE) {
        SetOpen(false, "Escape");
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

// a MODS entry was chosen, the main menu's or a pause menu's (src/fci_mainmenu.c, from the game's thread)
extern "C" void fci_overlay_open_from_menu(const char* by)
{
    if (g_ready)
        SetOpen(true, by);
    else
        std::fprintf(stderr, "[FCI] mod menu: MODS chosen, but the menu has no window\n");
}

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
    // the sticks of a controller (or a test script) only: the report carries the keyboard's bindings too,
    // and their stick clicks, crouch (Shift) and zoom (middle mouse button), are held together in play
    bool both = (report[2] & kThumbs) == kThumbs && !fci_input_stick_click_held();
    if (both && !chord[pad])
        SetOpen(!g_open, "both sticks");
    chord[pad] = both;
    bool b = report[5] > 0x40;
    if (g_open && b && !b_down[pad])
        SetOpen(false, "B");
    b_down[pad] = b;
    if (pad == 0 && g_steer_wait && !Pressed(report))
        g_steer_wait = false;
    if (pad == 0 && (g_open || steering)) {
        PadToMenu(report, g_open && !both && !g_steer_wait);
        steering = g_open;
    }
    if (!g_open && g_hold && !Pressed(report))
        g_hold = false;
    if (g_open || g_hold)
        std::memset(report + 2, 0, 18);
}
