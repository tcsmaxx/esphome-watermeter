#include "meter_setup.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/logger/logger.h"
#include "esphome/core/application.h"
#include "esphome/core/helpers.h"
#include <algorithm>
#include <ctime>
#include <cstdlib>
#include <cstring>
#ifdef USE_MQTT
#include "esphome/components/mqtt/mqtt_client.h"
#endif
namespace esphome::meter_setup {
void MeterSetup::features_setup_() {
  boot_started_=millis();
  for(auto &v:digit_confidences_)v=NAN;
  runtime_preference_=global_preferences->make_preference<RuntimeSettings>(0x7a32b908);
  RuntimeSettings saved;
  if(runtime_preference_.load(&saved)&&saved.version==1&&saved.warning_after>=30&&saved.warning_after<=86400)runtime_=saved;
  if(logger::global_logger)logger::global_logger->add_log_callback(this,[](void *owner,uint8_t,const char *tag,const char *message,size_t len){static_cast<MeterSetup*>(owner)->capture_digit_log_(tag,message,len);});
  build_export_();
}
void MeterSetup::capture_digit_log_(const char *tag,const char *message,size_t len) {
  if(!tag||std::strcmp(tag,"meter_reader_tflite")||!message)return;
  const std::string text(message,len);
  const auto result=text.find("Result: "),raw=text.find("Raw: "),list=text.find('[',raw);
  if(result==std::string::npos||raw==std::string::npos||list==std::string::npos)return;
  const std::string digits=text.substr(raw+5,8);
  if(digits.size()!=8||digits.find_first_not_of("0123456789")!=std::string::npos)return;
  float values[8];const char *p=text.c_str()+list+1;
  for(int i=0;i<8;i++) {char *end=nullptr;float value=std::strtof(p,&end);if(end==p||!std::isfinite(value)||value<0||value>1)return;
    while(*end==' ')++end;if(*end!=(i==7?']':','))return;values[i]=value*100;p=end+1;
  }
  std::lock_guard<std::mutex> lock(mutex_);
  if(!busy_||timed_out_)return;
  confidence_digits_=digits;std::copy(values,values+8,digit_confidences_);
}
void MeterSetup::features_loop_() {
  if(millis()-health_updated_>=5000) {
    health_updated_=millis();const auto epoch=std::time(nullptr);
    if(have_previous_reading_)reading_age_=(millis()-last_accepted_at_)/1000U;
    else if(runtime_.last_valid_epoch&&epoch>=runtime_.last_valid_epoch)reading_age_=uint32_t(epoch)-runtime_.last_valid_epoch;
    else reading_age_=NAN;
    stale_=settings_.calibrated&&(std::isfinite(reading_age_)?reading_age_>=runtime_.warning_after:millis()-boot_started_>=runtime_.warning_after*1000U);
    if(age_sensor_)age_sensor_->publish_state(reading_age_);
    if(stale_sensor_)stale_sensor_->publish_state(stale_);
  }
  mqtt_loop_();
}
void MeterSetup::build_export_() {
  static constexpr char hex[]="0123456789abcdef";
  std::string pixels;pixels.reserve(1024);for(const auto &row:alignment_.pixels)for(uint8_t b:row){pixels+=hex[b>>4];pixels+=hex[b&15];}
  export_json_=json::build_json([&](JsonObject root){
    root["format"]="esphome-watermeter";root["version"]=1;root["camera_width"]=640;root["camera_height"]=480;root["warning_after"]=runtime_.warning_after;
    auto s=root["settings"].to<JsonObject>();s["baseline"]=settings_.baseline;s["max_step"]=settings_.max_step;s["interval"]=settings_.interval;s["decimals"]=settings_.decimals;s["calibrated"]=bool(settings_.calibrated);
    auto boxes=s["boxes"].to<JsonArray>();for(const auto &box:settings_.boxes){auto row=boxes.add<JsonArray>();for(auto v:box)row.add(v);}
    auto a=root["alignment"].to<JsonObject>();a["enabled"]=bool(alignment_.enabled);a["ready"]=bool(alignment_.ready);a["pixels"]=pixels;
    auto regions=a["regions"].to<JsonArray>();for(const auto &box:alignment_.regions){auto row=regions.add<JsonArray>();for(auto v:box)row.add(v);}
    auto l=root["illumination"].to<JsonObject>();l["enabled"]=bool(illumination_settings_.enabled);l["brightness"]=illumination_settings_.brightness;l["settle_ms"]=illumination_settings_.settle_ms;l["led_count"]=illumination_settings_.led_count;
  });
}
void MeterSetup::import_config_() {
  Settings cfg;AlignmentReference refs;IlluminationSettings light;RuntimeSettings options;
  const auto uint_value=[](JsonVariant value,uint32_t min,uint32_t max,uint32_t &out){if(!value.is<uint32_t>())return false;out=value.as<uint32_t>();return out>=min&&out<=max;};
  const bool valid=json::parse_json(pending_import_,[&](JsonObject root){
    uint32_t header_value;
    if(!root["format"].is<const char*>()||std::strcmp(root["format"],"esphome-watermeter")||!uint_value(root["version"],1,1,header_value)||!uint_value(root["camera_width"],640,640,header_value)||!uint_value(root["camera_height"],480,480,header_value))return false;
    if(!uint_value(root["warning_after"],30,86400,options.warning_after))return false;
    auto s=root["settings"].as<JsonObject>();uint32_t v;
    if(!s["calibrated"].is<bool>()||!uint_value(s["baseline"],0,99999999,cfg.baseline)||!uint_value(s["max_step"],1,99999999,cfg.max_step)||!uint_value(s["interval"],10,86400,cfg.interval)||!uint_value(s["decimals"],0,6,v))return false;
    cfg.decimals=v;cfg.calibrated=s["calibrated"].as<bool>();auto boxes=s["boxes"].as<JsonArray>();if(boxes.size()!=8)return false;
    for(int i=0;i<8;i++){auto row=boxes[i].as<JsonArray>();if(row.size()!=4)return false;for(int j=0;j<4;j++){if(!uint_value(row[j],0,j%2?480:640,v))return false;cfg.boxes[i][j]=v;}}
    if(cfg.calibrated){if(!valid_(cfg))return false;}else for(const auto &box:cfg.boxes)for(auto value:box)if(value)return false;
    auto a=root["alignment"].as<JsonObject>();if(!a["enabled"].is<bool>()||!a["ready"].is<bool>()||!a["pixels"].is<const char*>())return false;
    refs.enabled=a["enabled"].as<bool>();refs.ready=a["ready"].as<bool>();auto regions=a["regions"].as<JsonArray>();if(regions.size()!=2)return false;
    for(int i=0;i<2;i++){auto row=regions[i].as<JsonArray>();if(row.size()!=4)return false;for(int j=0;j<4;j++){if(!uint_value(row[j],0,j%2?480:640,v))return false;refs.regions[i][j]=v;}}
    const std::string encoded=a["pixels"].as<const char*>();if(encoded.size()!=1024)return false;
    const auto nibble=[](char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;};
    for(int i=0;i<512;i++){int h=nibble(encoded[i*2]),l=nibble(encoded[i*2+1]);if(h<0||l<0)return false;refs.pixels[i/256][i%256]=(h<<4)|l;}
    if((refs.enabled&&!refs.ready)||((refs.enabled||refs.ready)&&!valid_reference_regions(refs)))return false;
    if(refs.ready)for(const auto &row:refs.pixels){float sum=0,sq=0;for(auto x:row){sum+=x;sq+=float(x)*x;}if(sq-sum*sum/256<256*64)return false;}
    auto l=root["illumination"].as<JsonObject>();if(!l["enabled"].is<bool>()||!uint_value(l["brightness"],1,100,v))return false;light.brightness=v;light.enabled=l["enabled"].as<bool>();
    if(!uint_value(l["settle_ms"],0,5000,v))return false;light.settle_ms=v;if(!uint_value(l["led_count"],1,led_capacity_(),v))return false;light.led_count=v;
    return true;
  });
  pending_import_.clear();
  if(!valid){message_="Import abgelehnt: ungültige oder inkompatible Sicherung";return;}
  const bool saved=save_configuration_(cfg,refs,false)&&illumination_preference_.save(&light)&&runtime_preference_.save(&options)&&global_preferences->sync();
  if(!saved){save_configuration_(settings_,alignment_,false);illumination_preference_.save(&illumination_settings_);runtime_preference_.save(&runtime_);global_preferences->sync();message_="Import fehlgeschlagen: Speicherung nicht möglich";return;}
  settings_=pending_=cfg;alignment_=draft_alignment_=pending_alignment_=refs;illumination_settings_=pending_illumination_=light;runtime_=options;
  paused_=true;accepted_=false;reading_problem_=false;reading_error_.clear();have_previous_reading_=false;reading_age_=NAN;stale_=false;boot_started_=millis();
  preview_.reset();inference_jpeg_.reset();preview_size_=inference_jpeg_size_=0;digits_.clear();confidence_digits_.clear();confidence_=0;
  light_test_=false;set_illumination_(false,illumination_settings_);
  if(cfg.calibrated){std::string zones="[";for(int i=0;i<8;i++){if(i)zones+=',';zones+='[';for(int j=0;j<4;j++){if(j)zones+=',';zones+=std::to_string(cfg.boxes[i][j]);}zones+=']';}zones+=']';reader_->set_crop_zones(zones);}
  ++config_revision_;message_="Sicherung importiert; Automatik pausiert. Rahmen testen und fortsetzen";build_export_();
}
void MeterSetup::mqtt_loop_() {
#ifdef USE_MQTT
  auto *client=mqtt::global_mqtt_client;if(!client||!client->is_connected()){mqtt_discovered_=false;return;}
  const auto &discovery=client->get_discovery_info();const auto prefix=client->get_topic_prefix();
  if(!mqtt_discovered_&&client->is_discovery_enabled()) {
    const auto topic=discovery.prefix+"/camera/"+App.get_name()+"/kamerabild/config";
    char mac_buffer[MAC_ADDRESS_BUFFER_SIZE];get_mac_address_into_buffer(mac_buffer);const std::string mac(mac_buffer);
    const auto payload=json::build_json([&](JsonObject root){root["name"]="Kamerabild";root["unique_id"]=mac+"-watermeter-camera";root["topic"]=prefix+"/camera/image";
      const auto &available=client->get_availability();if(!available.topic.empty()){root["availability_topic"]=available.topic;root["payload_available"]=available.payload_available;root["payload_not_available"]=available.payload_not_available;}
      auto device=root["device"].to<JsonObject>();device["identifiers"]=mac;device["name"]=App.get_friendly_name();device["manufacturer"]="ESPHome";device["model"]="XIAO ESP32-S3 Watermeter";
    });
    mqtt_discovered_=client->publish(topic,std::string(payload),0,discovery.retain);
  }
  if(!busy_&&!test_&&inference_jpeg_&&mqtt_image_sequence_!=preview_sequence_) {
    if(client->publish(prefix+"/camera/image",reinterpret_cast<const char*>(inference_jpeg_.get()),inference_jpeg_size_,0,true))mqtt_image_sequence_=preview_sequence_;
  }
#endif
}
}
