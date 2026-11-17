#ifndef BANKS_H
#define BANKS_H

#define BANK_COUNT 40
#define BANK_NAME_SIZE 96

enum PathState { PATH_ERROR = -1, PATH_MISSING, PATH_DIRECTORY, PATH_OTHER };
enum ScanWarning {
    WARN_IO = 1, WARN_CONFIG = 2, WARN_ACTIVE_MISSING = 4,
    WARN_CONFLICT = 8, WARN_LIMIT = 16, WARN_UNEXPECTED = 32
};
typedef struct {
    char name[BANK_NAME_SIZE];
    enum PathState stored;
} Bank;
typedef struct {
    Bank banks[BANK_COUNT];
    int active; /* -1 means unverified/unknown; never assume slot zero. */
    enum PathState root, bank_dir, live_dir;
    unsigned warnings;
    unsigned stored_count;
    int config_found;
} BankScan;

/* root is "sdmc:" on hardware, a temporary fixture directory in host tests.
 * Only directory metadata and /3DSBank/3DSBank.ini are read. */
void banks_scan(const char *root, BankScan *scan);
const char *banks_status(const BankScan *scan, int slot);
#endif
