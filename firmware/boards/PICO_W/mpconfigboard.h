// Pico Segment on a Raspberry Pi Pico W: the stock RPI_PICO_W board
// plus a USB drive. See ../PICO/mpconfigboard.h for the why; the
// wireless lines below are copied from the stock board unchanged.

#define MICROPY_HW_BOARD_NAME                   "Pico Segment (Pico W)"
#define MICROPY_HW_FLASH_STORAGE_BYTES          (848 * 1024)

// USB mass storage over the FAT filesystem.
#define MICROPY_HW_USB_MSC                      (1)
#define MICROPY_HW_FLASH_FS_LABEL               "PICOSEGMENT"   // 11 chars, FAT max

// How the drive introduces itself.
#define MICROPY_HW_USB_MANUFACTURER_STRING      "Retro City"
#define MICROPY_HW_USB_PRODUCT_FS_STRING        "Pico Segment"
#define MICROPY_HW_USB_MSC_INQUIRY_VENDOR_STRING   "RetroCty"   // 8 chars max
#define MICROPY_HW_USB_MSC_INQUIRY_PRODUCT_STRING  "Pico Segment"
#define MICROPY_HW_USB_MSC_INQUIRY_REVISION_STRING "1.0"

// --- as the stock RPI_PICO_W board -------------------------------------

// Enable networking.
#define MICROPY_PY_NETWORK 1
#define MICROPY_PY_NETWORK_HOSTNAME_DEFAULT     "PicoW"

// CYW43 driver configuration.
#define CYW43_USE_SPI (1)
#define CYW43_LWIP (1)
#define CYW43_GPIO (1)
#define CYW43_SPI_PIO (1)

#define MICROPY_HW_PIN_EXT_COUNT    CYW43_WL_GPIO_COUNT

// If this returns true for a pin then its irq will not be disabled on a soft reboot
int mp_hal_is_pin_reserved(int n);
#define MICROPY_HW_PIN_RESERVED(i) mp_hal_is_pin_reserved(i)
