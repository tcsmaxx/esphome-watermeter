#include "meter_setup.h"
#include "preview_jpeg.h"
#include "esp_jpeg_enc.h"
#include "esphome/core/log.h"
#include <cstring>
namespace esphome::meter_setup {
PreviewJpeg encode_preview_jpeg(const uint8_t *rgb,size_t size){
  if(!rgb||size!=640*480*3)return {};
  jpeg_enc_config_t config=DEFAULT_JPEG_ENC_CONFIG();config.width=640;config.height=480;config.src_type=JPEG_PIXEL_FORMAT_RGB888;config.quality=95;config.subsampling=JPEG_SUBSAMPLE_444;
  jpeg_enc_handle_t encoder=nullptr;if(jpeg_enc_open(&config,&encoder)!=JPEG_ERR_OK)return {};
  constexpr size_t capacity=384*1024;
  auto bytes=std::shared_ptr<uint8_t>(static_cast<uint8_t*>(heap_caps_aligned_alloc(16,capacity,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),heap_caps_free);
  int length=0;const bool ok=bytes&&jpeg_enc_process(encoder,const_cast<uint8_t*>(rgb),size,bytes.get(),capacity,&length)==JPEG_ERR_OK&&length>0&&size_t(length)<=capacity;
  jpeg_enc_close(encoder);if(!ok)return {};
  // Keep only the encoded size once the larger working buffer can be released.
  auto compact=std::shared_ptr<uint8_t>(static_cast<uint8_t*>(heap_caps_malloc(length,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),heap_caps_free);
  if(compact){std::memcpy(compact.get(),bytes.get(),length);return {std::move(compact),size_t(length)};}
  return {std::move(bytes),size_t(length)};
}
void MeterSetup::prepare_preview_(){
  preview_encode_pending_=false;
  if(!preview_||!preview_rgb_)return;
  auto encoded=encode_preview_jpeg(preview_.get(),preview_size_);
  preview_jpeg_sequence_=preview_sequence_;preview_encode_failed_=!encoded.data;
  preview_jpeg_=std::move(encoded.data);preview_jpeg_size_=encoded.size;
  if(preview_encode_failed_)ESP_LOGW("meter_setup","KI-Vorschau konnte nicht als JPEG vorbereitet werden (Bildspeicher/Codec)");
}
}
