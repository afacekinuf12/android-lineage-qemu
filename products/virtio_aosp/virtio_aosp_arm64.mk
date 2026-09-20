# A standalone VirtIO product. Device sources retain their upstream licenses.
# Install this directory at vendor/virtio_aosp in the Android source tree.
ifneq ($(strip $(LINEAGE_BUILD)),)
$(error virtio_aosp_arm64 requires an AOSP build environment; LINEAGE_BUILD is set)
endif

# AOSP does not supply the device tree's Lineage kernel-page-size default.
# Select the exact validated prebuilt before its PRODUCT_COPY_FILES are read.
TARGET_PREBUILT_KERNEL_ARCH := arm64
TARGET_PREBUILT_KERNEL_PAGE_SIZE := 4k

# Keep the upstream AOSP app, framework and provider dependency graph together.
# This file does not inherit a Lineage product or selectively uninstall its SDK.
$(call inherit-product, device/virt/virtio_arm64only/aosp_virtio_arm64only.mk)

PRODUCT_NAME := virtio_aosp_arm64
PRODUCT_DEVICE := virtio_arm64only
PRODUCT_BRAND := VirtIO
PRODUCT_MANUFACTURER := VirtIO
PRODUCT_MODEL := VirtIO ARM64

# Private keys must be explicitly provisioned for this product. Do not inherit
# vendor/lineage/config/common.mk just to obtain its certificate settings.
ifeq ($(wildcard vendor/virtio_aosp/keys/releasekey.x509.pem),)
$(error Provision vendor/virtio_aosp/keys using scripts/prepare-aosp-keys.sh)
endif
PRODUCT_DEFAULT_DEV_CERTIFICATE := vendor/virtio_aosp/keys/releasekey

# Fingerprint, build ID, incremental, release and tags remain build-generated.
# A newly installed AOSP product must enforce its own privileged-app allowlist.
PRODUCT_PRODUCT_PROPERTIES += ro.control_privapp_permissions=enforce
