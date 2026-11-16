#include <3ds.h>
#include <stdio.h>
#include <string.h>
#include "banks.h"

static void draw(PrintConsole *top, PrintConsole *bottom, const BankScan *scan, int selected)
{
    consoleSelect(top);
    consoleClear();
    printf("3DSBank Manager v0.1\nREAD-ONLY experimental scanner\n\n");
    if (scan->root != PATH_DIRECTORY) printf("SD card unavailable / unreadable\n");
    else printf("Stored directories: %u\n", scan->stored_count);
    if (scan->active < 0) printf("Active slot: unknown\n");
    else printf("INI selected slot: %d\n", scan->active);
    printf("/Nintendo 3DS: %s\n", scan->live_dir == PATH_DIRECTORY ? "present" :
        scan->live_dir == PATH_MISSING ? "absent" : "unavailable");
    printf("\nDiagnostics: %s\n", scan->warnings ? "check below" : "OK");
    if (scan->warnings & WARN_IO) printf("- Missing/unreadable SD or bank path\n");
    if (scan->warnings & WARN_CONFIG) printf("- INI missing/invalid; active uncertain\n");
    if (scan->warnings & WARN_ACTIVE_MISSING) printf("- INI active folder is missing\n");
    if (scan->warnings & WARN_CONFLICT) printf("- Selected slot also has stored path\n");
    if (scan->warnings & WARN_LIMIT) printf("- Metadata truncated or oversized\n");
    if (scan->warnings & WARN_UNEXPECTED) printf("- Unexpected bank entry / file\n");
    printf("\nNo transfers or bank switching.\nNo NAND, title, game or save writes.\n");
    consoleSelect(bottom);
    consoleClear();
    printf("Banks %d-%d / 0-39\n\n", (selected / 8) * 8, (selected / 8) * 8 + 7);
    for (int i = (selected / 8) * 8; i < (selected / 8) * 8 + 8; ++i)
        printf("%c%02d %-21.21s\n    %s\n", i == selected ? '>' : ' ', i,
               scan->banks[i].name, banks_status(scan, i));
    const char *name = scan->banks[selected].name;
    size_t len = strlen(name);
    printf("\nSelected name:\n%.35s\n%.35s\n%.25s\n", name,
           name + (len > 35 ? 35 : len), name + (len > 70 ? 70 : len));
    printf("\nUP/DOWN: browse  X: rescan\nSTART: exit\n");
}

int main(void)
{
    PrintConsole top, bottom;
    BankScan scan;
    int selected = 0;
    gfxInitDefault();
    consoleInit(GFX_TOP, &top);
    consoleInit(GFX_BOTTOM, &bottom);
    banks_scan("sdmc:", &scan);
    draw(&top, &bottom, &scan, selected);
    while (aptMainLoop()) {
        hidScanInput();
        u32 keys = hidKeysDown();
        if (keys & KEY_START) break;
        int changed = 0;
        if ((keys & KEY_UP) && selected > 0) { --selected; changed = 1; }
        if ((keys & KEY_DOWN) && selected < BANK_COUNT - 1) { ++selected; changed = 1; }
        if (keys & KEY_X) { banks_scan("sdmc:", &scan); changed = 1; }
        if (changed) draw(&top, &bottom, &scan, selected);
        gfxFlushBuffers();
        gfxSwapBuffers();
        gspWaitForVBlank();
    }
    gfxExit();
    return 0;
}
