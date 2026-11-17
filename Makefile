# Native C application, using devkitPro's maintained 3DS rules.
.DEFAULT_GOAL := all
.SUFFIXES:
ifeq ($(strip $(DEVKITARM)),)
$(error Set DEVKITARM; install devkitPro 3ds-dev or use devkitpro/devkitarm)
endif
include $(DEVKITARM)/3ds_rules

TARGET := 3DSBankManager
BUILD := build
ARCH := -march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft
CFLAGS := -g -Wall -Wextra -Werror -O2 -std=gnu11 -mword-relocations \
          -ffunction-sections $(ARCH) $(INCLUDE) -D__3DS__
LDFLAGS = -specs=3dsx.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)
LIBS := -lctru -lm
LIBDIRS := $(CTRULIB)
export APP_TITLE := 3DSBank Manager
export APP_DESCRIPTION := v0.1 read-only slot scanner
export APP_AUTHOR := Blaku792

ifneq ($(BUILD),$(notdir $(CURDIR)))
export TOPDIR := $(CURDIR)
export OUTPUT := $(CURDIR)/$(TARGET)
export VPATH := $(CURDIR)/source
export DEPSDIR := $(CURDIR)/$(BUILD)
export LD := $(CC)
export OFILES := banks.o main.o
export INCLUDE := -I$(CURDIR)/include $(foreach dir,$(LIBDIRS),-I$(dir)/include)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)
export _3DSXDEPS := $(OUTPUT).smdh
export _3DSXFLAGS := --smdh=$(OUTPUT).smdh
.PHONY: all clean
all: $(BUILD)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(TOPDIR)/Makefile
$(BUILD):
	@mkdir -p $@
clean:
	rm -rf $(BUILD) $(TARGET).3dsx $(TARGET).smdh $(TARGET).elf
else
.DEFAULT_GOAL := $(OUTPUT).3dsx
$(OUTPUT).3dsx: $(OUTPUT).elf $(_3DSXDEPS)
$(OUTPUT).elf: $(OFILES)
-include $(DEPSDIR)/*.d
endif
