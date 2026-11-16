#include <stdio.h>
#include "banks.h"
int main(int argc, char **argv)
{
    BankScan scan;
    if (argc != 2) return 2;
    banks_scan(argv[1], &scan);
    printf("active=%d stored=%u warnings=%u config=%d root=%d live=%d\n",
           scan.active, scan.stored_count, scan.warnings, scan.config_found, scan.root, scan.live_dir);
    for (int i = 0; i < BANK_COUNT; ++i)
        printf("%d|%s|%s\n", i, scan.banks[i].name, banks_status(&scan, i));
    return 0;
}
