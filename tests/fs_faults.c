/* Test-only GNU ld wrappers: never linked into the 3DS application. */
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static int fault(const char *name)
{
    const char *value = getenv("BANK_TEST_FAULT");
    return value && strcmp(value, name) == 0;
}

FILE *__real_fopen(const char *, const char *);
FILE *__wrap_fopen(const char *path, const char *mode)
{
    const char suffix[] = "/3DSBank/3DSBank.ini";
    size_t len = strlen(path);
    /* Check operation arguments as well as the import allowlist. */
    if (strcmp(mode, "rb") || len < sizeof(suffix) - 1 ||
        strcmp(path + len - (sizeof(suffix) - 1), suffix)) abort();
    if (fault("fopen")) { errno = EACCES; return NULL; }
    return __real_fopen(path, mode);
}

int __real_stat(const char *, struct stat *);
int __wrap_stat(const char *path, struct stat *st)
{
    if (fault("stat") && strstr(path, "/Slot7")) { errno = EIO; return -1; }
    return __real_stat(path, st);
}

DIR *__real_opendir(const char *);
DIR *__wrap_opendir(const char *path)
{
    if (fault("opendir")) { errno = EACCES; return NULL; }
    return __real_opendir(path);
}

struct dirent *__real_readdir(DIR *);
struct dirent *__wrap_readdir(DIR *dir)
{
    if (fault("readdir")) { errno = EIO; return NULL; }
    if (fault("overflow-entry")) {
        /* Deterministically return overflow last, immediately before EOF. */
        static int end;
        static struct dirent entry;
        if (end) return NULL;
        end = 1;
        memset(&entry, 0, sizeof(entry));
        strcpy(entry.d_name, "Slot99999999999999999999999999999999999");
        return &entry;
    }
    return __real_readdir(dir);
}

int __real_fgetc(FILE *);
int __wrap_fgetc(FILE *file)
{
    /* Simulate a late read error after a valid active selection was read. */
    static unsigned reads;
    if (fault("fgetc") && ++reads > 30) { errno = EIO; return EOF; }
    return __real_fgetc(file);
}

int __real_ferror(FILE *);
int __wrap_ferror(FILE *file)
{
    return fault("fgetc") ? 1 : __real_ferror(file);
}
