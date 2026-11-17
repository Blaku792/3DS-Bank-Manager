#include "banks.h"
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define SCAN_PATH_SIZE 512
#define INI_BYTE_LIMIT 65536

static int path_join(char *out, size_t size, const char *root, const char *suffix)
{
    int n = snprintf(out, size, "%s/%s", root, suffix);
    return n >= 0 && (size_t)n < size;
}

static enum PathState inspect(const char *path, unsigned *warnings)
{
    struct stat st;
    if (stat(path, &st) == 0)
        return S_ISDIR(st.st_mode) ? PATH_DIRECTORY : PATH_OTHER;
    if (errno == ENOENT) return PATH_MISSING;
    *warnings |= WARN_IO;
    return PATH_ERROR;
}

static char *trim(char *s)
{
    char *end;
    /* Upstream trims only spaces and horizontal tabs, not C isspace(). */
    while (*s == ' ' || *s == '\t') ++s;
    end = s + strlen(s);
    while (end > s && (end[-1] == ' ' || end[-1] == '\t')) --end;
    *end = '\0';
    return s;
}

static int invalid_structure(const char *s)
{
    int header = *s == '[';
    /* Check headers (including annotations) and keys before interpreting them.
     * CR/LF have already delimited lines. Alias values are sanitized separately. */
    for (; *s && (header || *s != '='); ++s) {
        unsigned char c = (unsigned char)*s;
        if ((c < 32 && c != '\t') || c == 127) return 1;
    }
    return 0;
}

static int slot_number(const char *s)
{
    char *end;
    long n;
    if (!isdigit((unsigned char)*s)) return -1;
    errno = 0;
    n = strtol(s, &end, 10);
    if (errno || *end || n < 0 || n >= BANK_COUNT) return -1;
    return (int)n;
}

static void read_config(const char *path, BankScan *scan)
{
    FILE *file = fopen(path, "rb");
    char line[512];
    unsigned bytes = 0;
    int section = 0, section_seen = 0, active_seen = 0, bad_active = 0;
    unsigned char names_seen[BANK_COUNT] = {0};
    if (!file) {
        if (errno != ENOENT) scan->warnings |= WARN_IO;
        scan->warnings |= WARN_CONFIG;
        return;
    }
    scan->config_found = 1;
    /* Read bounded lines, rejecting embedded NULs and overlong lines. */
    while (bytes < INI_BYTE_LIMIT) {
        int first_line = bytes == 0;
        size_t used = 0;
        int c, overflow = 0, nul = 0;
        while ((c = fgetc(file)) != EOF) {
            ++bytes;
            if (c == '\n' || c == '\r') break;
            if (c == 0) nul = 1;
            if (used + 1 < sizeof(line)) line[used++] = (char)c;
            else overflow = 1;
            if (bytes >= INI_BYTE_LIMIT) break;
        }
        if (c == EOF && used == 0 && !overflow) break;
        line[used] = '\0';
        if (overflow || nul || bytes >= INI_BYTE_LIMIT) {
            scan->warnings |= WARN_CONFIG | WARN_LIMIT;
            /* Unread or malformed metadata may contain a conflicting selection. */
            bad_active = 1;
            section = 0;
            continue;
        }
        char *s = line;
        if (first_line && used >= 3 &&
            (unsigned char)s[0] == 0xef && (unsigned char)s[1] == 0xbb &&
            (unsigned char)s[2] == 0xbf) s += 3;
        s = trim(s);
        if (!*s || *s == ';' || *s == '#' || *s == '/' || *s == '!') continue;
        if (invalid_structure(s)) {
            scan->warnings |= WARN_CONFIG;
            bad_active = 1;
            section = 0;
            continue;
        }
        if (*s == '[') {
            /* Upstream compares text through the first closing bracket, ignoring
             * suffix annotations. Count matching sections, even empty ones. */
            char *close = strchr(s, ']');
            if (!close) {
                bad_active = 1;
                scan->warnings |= WARN_CONFIG;
                section = 0;
                continue;
            }
            /* Upstream's inner key loop can interpret '=' header annotations
             * as keys instead of boundaries. Do not infer a selection there. */
            if (section && strchr(close + 1, '=')) bad_active = 1;
            *close = '\0';
            section = strcmp(s + 1, "3DSBANK") == 0;
            if (section && section_seen++) {
                bad_active = 1;
                scan->warnings |= WARN_CONFIG;
                section = 0; /* Do not blend aliases from duplicate sections. */
            }
            continue;
        }
        if (!section) continue;
        char *equals = strchr(s, '=');
        if (!equals) { scan->warnings |= WARN_CONFIG; bad_active = 1; continue; }
        *equals = '\0';
        char *key = trim(s), *value = trim(equals + 1);
        if (strcmp(key, "FOLDER_SLOT") == 0) {
            int n = slot_number(value);
            if (active_seen++ || n < 0) {
                scan->warnings |= WARN_CONFIG;
                bad_active = 1;
            }
            scan->active = n;
        } else if (strncmp(key, "SLOT_NAME_", 10) == 0) {
            int n = slot_number(key + 10);
            if (n < 0) { scan->warnings |= WARN_CONFIG; continue; }
            /* Upstream looks up exact decimal keys; padded aliases must not
             * consume names_seen or shadow a later canonical spelling. */
            char canonical[24];
            snprintf(canonical, sizeof(canonical), "SLOT_NAME_%d", n);
            if (strcmp(key, canonical)) { scan->warnings |= WARN_CONFIG; continue; }
            if (names_seen[n]) { scan->warnings |= WARN_CONFIG; continue; }
            names_seen[n] = 1;
            size_t len = strlen(value);
            if (len >= BANK_NAME_SIZE) scan->warnings |= WARN_LIMIT;
            snprintf(scan->banks[n].name, BANK_NAME_SIZE, "%.*s", BANK_NAME_SIZE - 1, value);
            /* Prevent terminal control injection; v0.1 displays ASCII aliases. */
            for (char *p = scan->banks[n].name; *p; ++p)
                if ((unsigned char)*p < 32 || (unsigned char)*p > 126) *p = '?';
        }
    }
    if (ferror(file)) { scan->warnings |= WARN_IO; bad_active = 1; }
    fclose(file);
    if (!active_seen || bad_active) {
        scan->active = -1;
        scan->warnings |= WARN_CONFIG;
    }
}

void banks_scan(const char *root, BankScan *scan)
{
    char path[SCAN_PATH_SIZE], suffix[64];
    memset(scan, 0, sizeof(*scan));
    scan->active = -1;
    scan->live_dir = scan->bank_dir = PATH_ERROR;
    for (int i = 0; i < BANK_COUNT; ++i) {
        scan->banks[i].stored = PATH_ERROR;
        snprintf(scan->banks[i].name, BANK_NAME_SIZE, "Slot %d", i);
    }
    scan->root = inspect(root, &scan->warnings);
    if (scan->root != PATH_DIRECTORY) { scan->warnings |= WARN_IO; return; }
    if (!path_join(path, sizeof(path), root, "3DSBank/3DSBank.ini")) {
        scan->warnings |= WARN_LIMIT | WARN_IO; return;
    }
    read_config(path, scan);
    path_join(path, sizeof(path), root, "Nintendo 3DS");
    scan->live_dir = inspect(path, &scan->warnings);
    path_join(path, sizeof(path), root, "3DSBank");
    scan->bank_dir = inspect(path, &scan->warnings);
    if (scan->bank_dir != PATH_DIRECTORY) scan->warnings |= WARN_IO;
    /* Enumerate names only to diagnose unsupported/unexpected entries. Never recurse. */
    DIR *dir = opendir(path);
    if (dir) {
        for (;;) {
            /* strtol and other entry processing may set errno. Only a failing
             * readdir may turn that value into a directory I/O diagnostic. */
            errno = 0;
            struct dirent *entry = readdir(dir);
            if (!entry) {
                if (errno) scan->warnings |= WARN_IO;
                break;
            }
            const char *name = entry->d_name;
            if (strcmp(name, ".") && strcmp(name, "..") && strcmp(name, "3DSBank.ini")) {
                int n = strncmp(name, "Slot", 4) ? -1 : slot_number(name + 4);
                char canonical[16];
                snprintf(canonical, sizeof(canonical), "Slot%d", n);
                if (n < 0 || strcmp(name, canonical)) scan->warnings |= WARN_UNEXPECTED;
            }
        }
        closedir(dir);
    } else if (scan->bank_dir == PATH_DIRECTORY) scan->warnings |= WARN_IO;
    for (int i = 0; i < BANK_COUNT; ++i) {
        snprintf(suffix, sizeof(suffix), "3DSBank/Slot%d", i);
        path_join(path, sizeof(path), root, suffix);
        scan->banks[i].stored = inspect(path, &scan->warnings);
        if (scan->banks[i].stored == PATH_DIRECTORY) ++scan->stored_count;
        if (scan->banks[i].stored == PATH_OTHER) scan->warnings |= WARN_UNEXPECTED;
    }
    if (scan->active >= 0) {
        if (scan->live_dir != PATH_DIRECTORY) scan->warnings |= WARN_ACTIVE_MISSING;
        if (scan->banks[scan->active].stored != PATH_MISSING) scan->warnings |= WARN_CONFLICT;
    }
}

const char *banks_status(const BankScan *scan, int slot)
{
    if (slot < 0 || slot >= BANK_COUNT) return "invalid";
    if (scan->active == slot) {
        if (scan->banks[slot].stored != PATH_MISSING) return "CONFLICT";
        if (scan->live_dir == PATH_DIRECTORY) return "active (INI)";
        return "active missing";
    }
    switch (scan->banks[slot].stored) {
        case PATH_DIRECTORY: return "stored";
        case PATH_OTHER: return "not directory";
        case PATH_ERROR: return "read error";
        default: return "absent";
    }
}
