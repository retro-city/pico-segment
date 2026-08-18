// Pico Segment on a plain Raspberry Pi Pico: the stock RPI_PICO board
// plus a USB drive. The panel's code is frozen into the image, so the
// drive holds only settings.json and boot.wav -- edit those from any
// computer, no tools needed.
//
// MSC hands the host the raw filesystem region and the device's FatFs
// shares it with no locking, so main.py treats the drive as the PC's
// while a host is attached (see usb_host_present there).

#define MICROPY_HW_BOARD_NAME                   "Pico Segment"
#define MICROPY_HW_FLASH_STORAGE_BYTES          (1408 * 1024)

// USB mass storage over the FAT filesystem.
#define MICROPY_HW_USB_MSC                      (1)
#define MICROPY_HW_FLASH_FS_LABEL               "PICOSEGMENT"   // 11 chars, FAT max

// How the drive introduces itself.
#define MICROPY_HW_USB_MANUFACTURER_STRING      "Retro City"
#define MICROPY_HW_USB_PRODUCT_FS_STRING        "Pico Segment"
#define MICROPY_HW_USB_MSC_INQUIRY_VENDOR_STRING   "RetroCty"   // 8 chars max
#define MICROPY_HW_USB_MSC_INQUIRY_PRODUCT_STRING  "Pico Segment"
#define MICROPY_HW_USB_MSC_INQUIRY_REVISION_STRING "1.0"
