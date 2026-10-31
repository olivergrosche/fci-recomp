/* Mods: replacement files for the game's archives, switched on in the mod menu (fci_mods.c, xbr/fci_overlay.cpp) */
#ifndef FCI_MODS_H
#define FCI_MODS_H

#ifdef __cplusplus
extern "C" {
#endif

/* before the game opens a file: reads the mods, merges their archives, redirects the kernel to them */
void fci_mods_init(const char *game_dir);
int fci_mods_count(void);
const char *fci_mods_id(int i); /* UTF-8, like the rest */
const char *fci_mods_name(int i);
const char *fci_mods_group(int i);
const char *fci_mods_description(int i);
const char *fci_mods_credit(int i);
int fci_mods_files(int i);           /* the files it replaces */
int fci_mods_enabled(int i);         /* chosen in the menu (mods\enabled.txt) */
int fci_mods_active(int i);          /* in this instance's archives */
int fci_mods_conflict(int i, int j); /* both replace a file */
void fci_mods_set(int i, int on);    /* on also switches off what conflicts with it; saved at once */
int fci_mods_pending(void);          /* the choice differs from what this instance runs with */
const char *fci_mods_folder(void);   /* where the mods are looked for */

/* The menu's settings (mods\settings.ini, read at start, saved at once, in effect at once; with no mods
 * too), in percent: the damage Jack deals to characters and the damage others deal to him (fci_damage.c) */
#define FCI_STRENGTH_MIN  25
#define FCI_STRENGTH_MAX  200
#define FCI_STRENGTH_STEP 5
int fci_mods_weapon_strength(void);
int fci_mods_enemy_damage(void);
void fci_mods_set_strengths(int weapon, int enemy); /* rounded to the step, kept in range */

#ifdef __cplusplus
}
#endif
#endif
