#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
namespace esphome::meter_setup {
struct PreviewJpeg {std::shared_ptr<uint8_t> data;size_t size{0};};
PreviewJpeg encode_preview_jpeg(const uint8_t *rgb,size_t size);
}
