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
  const auto end=text.find(',',raw+5);if(end==std::string::npos)return;
  const std::string digits=text.substr(raw+5,end-raw-5);
  const auto count=digits.size();
  if(count<1||count>MAX_DIGITS||digits.find_first_not_of("0123456789")!=std::string::npos)return;
  float values[MAX_DIGITS]{};const char *p=text.c_str()+list+1;
  for(size_t i=0;i<count;i++) {char *end=nullptr;float value=std::strtof(p,&end);if(end==p||!std::isfinite(value)||value<0||value>1)return;
    while(*end==' ')++end;if(*end!=(i==count-1?']':','))return;values[i]=value*100;p=end+1;
  }
  capture_digit_scores_(digits,values);
}
void MeterSetup::capture_digit_scores_(const std::string &digits,const float *values) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(timed_out_||digits.size()!=(test_?pending_:settings_).digit_count)return;
  // Logger delivery may follow the deferred reading callback. Match that result
  // for a bounded period, rather than discarding it because busy was cleared.
  if(!busy_&&(!confidence_pending_||digits!=digits_||millis()-confidence_finished_at_>3000))return;
  confidence_digits_=digits;std::copy(values,values+digits.size(),digit_confidences_);
  if(!busy_){for(int i=0;i<MAX_DIGITS;i++)if(digit_sensors_[i])digit_sensors_[i]->publish_state(i<digits.size()?values[i]:NAN);confidence_pending_=false;}
}
void AlignedMeterReader::loop() {
#ifdef SUPPORT_DOUBLE_BUFFERING
  // The main loop is the sole consumer. Read the result before the upstream
  // reader removes and releases it, preserving the original inference scores.
  InferenceResult *result=nullptr;
  if(owner_&&output_queue_&&xQueuePeek(output_queue_,&result,0)==pdTRUE&&result&&!result->readings.empty()&&result->readings.size()<=MAX_DIGITS&&result->probabilities.size()==result->readings.size()) {
    std::string digits;float values[MAX_DIGITS]{};bool valid=true;
    for(size_t i=0;i<result->readings.size();i++) {
      const float reading=result->readings[i],score=result->probabilities[i];
      if(!std::isfinite(reading)||reading<0||reading>=10||!std::isfinite(score)||score<0||score>1){valid=false;break;}
      int digit=(reading-std::floor(reading)>=0.7f)?int(std::ceil(reading)):int(std::floor(reading));
      digits+=char('0'+(digit>=10?0:digit));values[i]=score*100;
    }
    if(valid)owner_->capture_digit_scores_(digits,values);
  }
#endif
  MeterReaderTFLite::loop();
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
    root["format"]="esphome-watermeter";root["version"]=1;root["camera_width"]=640;root["camera_height"]=480;root["warning_after"]=runtime_.warning_after;root["autofocus_before_reading"]=bool(autofocus_settings_.before_reading);root["manual_focus_enabled"]=bool(autofocus_settings_.manual_enabled);root["manual_focus_position"]=autofocus_settings_.position;root["camera_standby"]=camera_power_.standby_enabled();root["camera_weak_drive"]=camera_power_.weak_drive();
    auto image=root["image"].to<JsonObject>();image["exposure"]=image_settings_.exposure;image["contrast"]=image_settings_.contrast;image["saturation"]=image_settings_.saturation;image["white_balance"]=image_settings_.white_balance;
    auto s=root["settings"].to<JsonObject>();s["digit_count"]=settings_.digit_count;s["rotation_tenths"]=settings_.rotation_tenths;s["baseline"]=settings_.baseline;s["max_step"]=settings_.max_step;s["interval"]=settings_.interval;s["decimals"]=settings_.decimals;s["calibrated"]=bool(settings_.calibrated);
    auto boxes=s["boxes"].to<JsonArray>();for(int i=0;i<settings_.digit_count;i++){auto row=boxes.add<JsonArray>();for(auto v:settings_.boxes[i])row.add(v);}
    auto a=root["alignment"].to<JsonObject>();a["enabled"]=bool(alignment_.enabled);a["ready"]=bool(alignment_.ready);a["pixels"]=pixels;
    auto regions=a["regions"].to<JsonArray>();for(const auto &box:alignment_.regions){auto row=regions.add<JsonArray>();for(auto v:box)row.add(v);}
    auto l=root["illumination"].to<JsonObject>();l["enabled"]=bool(illumination_settings_.enabled);l["brightness"]=illumination_settings_.brightness;l["settle_ms"]=illumination_settings_.settle_ms;l["led_count"]=illumination_settings_.led_count;l["led_mask"]=format_led_mask(illumination_settings_.led_mask);
  });
}
void MeterSetup::import_config_() {
  Settings cfg;ImageSettings image=image_settings_;AlignmentReference refs;IlluminationSettings light;RuntimeSettings options;auto focus=autofocus_settings_;const bool old_standby=camera_power_.standby_enabled(),old_weak=camera_power_.weak_drive();bool standby=old_standby,weak=old_weak;
  const auto uint_value=[](JsonVariant value,uint32_t min,uint32_t max,uint32_t &out){if(!value.is<uint32_t>())return false;out=value.as<uint32_t>();return out>=min&&out<=max;};
  const bool valid=json::parse_json(pending_import_,[&](JsonObject root){
    uint32_t header_value;
    if(!root["format"].is<const char*>()||std::strcmp(root["format"],"esphome-watermeter")||!uint_value(root["version"],1,1,header_value)||!uint_value(root["camera_width"],640,640,header_value)||!uint_value(root["camera_height"],480,480,header_value))return false;
    if(!root["camera_standby"].isNull()){if(!root["camera_standby"].is<bool>())return false;standby=root["camera_standby"].as<bool>();}
    if(!root["camera_weak_drive"].isNull()){if(!root["camera_weak_drive"].is<bool>())return false;weak=root["camera_weak_drive"].as<bool>();}
    if(!root["autofocus_before_reading"].isNull()){if(!root["autofocus_before_reading"].is<bool>())return false;focus.before_reading=root["autofocus_before_reading"].as<bool>();}
    if(!root["manual_focus_enabled"].isNull()){
      if(!root["manual_focus_enabled"].is<bool>())return false;focus.manual_enabled=root["manual_focus_enabled"].as<bool>();
      uint32_t position;if(!uint_value(root["manual_focus_position"],0,1023,position))return false;focus.position=position;
    }else if(!root["manual_focus_position"].isNull())return false;
    else if(!root["autofocus_before_reading"].isNull())focus.manual_enabled=0;
    if(focus.manual_enabled&&focus.before_reading)return false;
    if(!root["image"].isNull()){
      auto entry=root["image"];if(!entry.is<JsonObject>()||!entry["exposure"].is<int>()||!entry["contrast"].is<int>()||!entry["saturation"].is<int>()||!entry["white_balance"].is<int>())return false;
      const int exposure=entry["exposure"],contrast=entry["contrast"],saturation=entry["saturation"],wb=entry["white_balance"];
      if(exposure < -2||exposure>2||contrast < -2||contrast>2||saturation < -2||saturation>2||wb<0||wb>4)return false;
      image.exposure=exposure;image.contrast=contrast;image.saturation=saturation;image.white_balance=wb;
    }
    if(!uint_value(root["warning_after"],30,86400,options.warning_after))return false;
    auto s=root["settings"].as<JsonObject>();uint32_t v;
    if(!s["calibrated"].is<bool>()||!uint_value(s["baseline"],0,999999999,cfg.baseline)||!uint_value(s["max_step"],1,999999999,cfg.max_step)||!uint_value(s["interval"],10,86400,cfg.interval)||!uint_value(s["decimals"],0,6,v))return false;
    if(!s["rotation_tenths"].isNull()){
      if(!s["rotation_tenths"].is<int32_t>())return false;
      const auto angle=s["rotation_tenths"].as<int32_t>();if(angle < -1800||angle>1800)return false;cfg.rotation_tenths=angle;
    }
    refs.rotation_tenths=cfg.rotation_tenths;
    if(!s["digit_count"].isNull()){uint32_t count;if(!uint_value(s["digit_count"],1,MAX_DIGITS,count))return false;cfg.digit_count=count;}
    cfg.decimals=v;cfg.calibrated=s["calibrated"].as<bool>();auto boxes=s["boxes"].as<JsonArray>();if(boxes.size()!=cfg.digit_count)return false;
    for(int i=0;i<cfg.digit_count;i++){auto row=boxes[i].as<JsonArray>();if(row.size()!=4)return false;for(int j=0;j<4;j++){if(!uint_value(row[j],0,j%2?480:640,v))return false;cfg.boxes[i][j]=v;}}
    if(cfg.calibrated){if(!valid_(cfg))return false;}else if(!valid_draft_(cfg))return false;
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
    if(!l["led_mask"].isNull()&&(!l["led_mask"].is<const char*>()||!parse_led_mask(l["led_mask"].as<const char*>(),light.led_mask)))return false;
    return true;
  });
  pending_import_.clear();
  if(!valid){message_="Import abgelehnt: ungültige oder inkompatible Sicherung";return;}
  const bool saved=save_configuration_(cfg,refs,false)&&illumination_preference_.save(&light)&&image_preference_.save(&image)&&runtime_preference_.save(&options)&&autofocus_preference_.save(&focus)&&camera_power_.configure(standby,weak)&&global_preferences->sync();
  if(!saved){save_configuration_(settings_,alignment_,false);illumination_preference_.save(&illumination_settings_);image_preference_.save(&image_settings_);runtime_preference_.save(&runtime_);autofocus_preference_.save(&autofocus_settings_);camera_power_.configure(old_standby,old_weak);global_preferences->sync();message_="Import fehlgeschlagen: Speicherung nicht möglich";return;}
  settings_=pending_=cfg;image_settings_=pending_image_=image;alignment_=draft_alignment_=pending_alignment_=refs;illumination_settings_=pending_illumination_=light;runtime_=options;autofocus_settings_=focus;
  paused_=true;accepted_=false;reading_problem_=false;reading_error_.clear();have_previous_reading_=false;reading_age_=NAN;stale_=false;boot_started_=millis();
  preview_.reset();inference_jpeg_.reset();preview_size_=inference_jpeg_size_=0;digits_.clear();confidence_digits_.clear();confidence_=0;
  light_test_=false;set_illumination_(false,illumination_settings_);
  if(cfg.calibrated){std::string zones="[";for(int i=0;i<cfg.digit_count;i++){if(i)zones+=',';zones+='[';for(int j=0;j<4;j++){if(j)zones+=',';zones+=std::to_string(cfg.boxes[i][j]);}zones+=']';}zones+=']';reader_->set_crop_zones(zones);}
  mqtt_discovered_=false;mqtt_discovery_index_=0;mqtt_state_at_=0;
  for(int i=cfg.digit_count;i<MAX_DIGITS;i++)if(digit_sensors_[i])digit_sensors_[i]->publish_state(NAN);
  ++config_revision_;message_="Sicherung importiert; Automatik pausiert. Rahmen testen und fortsetzen";build_export_();
}
void MeterSetup::mqtt_loop_() {
#ifdef USE_MQTT
  auto *client=mqtt::global_mqtt_client;if(!client||!client->is_connected()){mqtt_discovered_=false;mqtt_discovery_index_=0;mqtt_state_at_=0;return;}
  const auto &discovery=client->get_discovery_info();const auto prefix=client->get_topic_prefix();
  struct Field {const char *key,*name,*domain,*unit,*device_class,*state_class;};
  static const Field fields[]={
    {"value","Zählerstand","sensor","m³","water","total_increasing"},
    {"change","Änderung zu Vorwert","sensor","m³","","measurement"},
    {"flow","Durchfluss","sensor","m³/h","","measurement"},
    {"last_update","Letzte Aktualisierung","sensor","","",""},
    {"status","Ablesestatus","sensor","","",""},
    {"error","Ablesefehler","sensor","","",""},
    {"age","Alter der letzten Ablesung","sensor","s","duration","measurement"},
    {"stale","Ablesung veraltet","binary_sensor","","problem",""},
    {"confidence","Erkennungskonfidenz","sensor","%","","measurement"},
    {"confidence_1","Konfidenz Stelle 1","sensor","%","","measurement"},
    {"confidence_2","Konfidenz Stelle 2","sensor","%","","measurement"},
    {"confidence_3","Konfidenz Stelle 3","sensor","%","","measurement"},
    {"confidence_4","Konfidenz Stelle 4","sensor","%","","measurement"},
    {"confidence_5","Konfidenz Stelle 5","sensor","%","","measurement"},
    {"confidence_6","Konfidenz Stelle 6","sensor","%","","measurement"},
    {"confidence_7","Konfidenz Stelle 7","sensor","%","","measurement"},
    {"confidence_8","Konfidenz Stelle 8","sensor","%","","measurement"},
    {"confidence_9","Konfidenz Stelle 9","sensor","%","","measurement"},
    {"problem","Ableseproblem","binary_sensor","","problem",""}};
  char mac_buffer[MAC_ADDRESS_BUFFER_SIZE];get_mac_address_into_buffer(mac_buffer);const std::string mac(mac_buffer);
  // Publish one discovery record per loop; retry failures without filling the outbox.
  if(!mqtt_discovered_&&client->is_discovery_enabled()) {
    const bool camera=mqtt_discovery_index_==0;
    const auto &field=fields[camera?0:mqtt_discovery_index_-1];
    const std::string key=camera?"kamerabild":field.key;
    const auto topic=discovery.prefix+"/"+(camera?"camera":field.domain)+"/"+App.get_name()+"/"+key+"/config";
    const bool inactive=!camera && key.rfind("confidence_",0)==0 && std::atoi(key.c_str()+11)>settings_.digit_count;
    const auto payload=inactive?std::string{}:json::build_json([&](JsonObject root){
      root["name"]=camera?"Kamerabild":field.name;root["unique_id"]=mac+"-watermeter-"+(camera?"camera":key);
      if(camera)root["topic"]=prefix+"/camera/image";
      else {
        root["state_topic"]=prefix+"/meter/state";
        root["value_template"]="{{ value_json."+key+" if value_json."+key+" is not none else 'None' }}";
        if(*field.unit)root["unit_of_measurement"]=field.unit;
        if(*field.device_class)root["device_class"]=field.device_class;
        if(*field.state_class)root["state_class"]=field.state_class;
        if(std::strcmp(field.domain,"binary_sensor")==0){root["value_template"]="{{ 'ON' if value_json."+key+" else 'OFF' }}";root["payload_on"]="ON";root["payload_off"]="OFF";}
        if(mqtt_discovery_index_>=7&&mqtt_discovery_index_<=18)root["entity_category"]="diagnostic";
      }
      const auto &available=client->get_availability();if(!available.topic.empty()){root["availability_topic"]=available.topic;root["payload_available"]=available.payload_available;root["payload_not_available"]=available.payload_not_available;}
      auto device=root["device"].to<JsonObject>();device["identifiers"]=mac;device["name"]=App.get_friendly_name();device["manufacturer"]="ESPHome";device["model"]="XIAO ESP32-S3 Watermeter";
    });
    if(client->publish(topic,std::string(payload),0,discovery.retain)){++mqtt_discovery_index_;mqtt_discovered_=mqtt_discovery_index_==20;}
  }
  if(!mqtt_state_at_||millis()-mqtt_state_at_>=5000) {
    const auto payload=json::build_json([&](JsonObject root){
      const auto number=[&](const char *key,sensor::Sensor *entity){if(entity&&entity->has_state()&&std::isfinite(entity->state))root[key]=entity->state;else root[key]=nullptr;};
      number("value",value_);number("change",change_);number("flow",flow_);number("age",age_sensor_);number("confidence",confidence_sensor_);
      for(int i=0;i<MAX_DIGITS;i++)number(("confidence_"+std::to_string(i+1)).c_str(),i<settings_.digit_count?digit_sensors_[i]:nullptr);
      root["last_update"]=last_update_?last_update_->state:"";root["status"]=status_sensor_?status_sensor_->state:"";root["error"]=error_sensor_?error_sensor_->state:"";
      root["stale"]=stale_;root["problem"]=!settings_.calibrated||reading_problem_||timed_out_||stale_;
    });
    if(client->publish(prefix+"/meter/state",std::string(payload),0,true))mqtt_state_at_=millis()?millis():1;
  }
  if(!busy_&&!test_&&inference_jpeg_&&mqtt_image_sequence_!=preview_sequence_) {
    if(timestamped_sequence_!=preview_sequence_){
      auto annotated=timestamp_jpeg(inference_jpeg_.get(),inference_jpeg_size_,inference_capture_epoch_);
      if(annotated.data){inference_jpeg_=std::move(annotated.data);inference_jpeg_size_=annotated.size;}
      else ESP_LOGW("meter_setup","Zeitstempel im MQTT-Bild fehlgeschlagen; Rohbild übertragen");
      timestamped_sequence_=preview_sequence_;
    }
    if(client->publish(prefix+"/camera/image",reinterpret_cast<const char*>(inference_jpeg_.get()),inference_jpeg_size_,0,true))mqtt_image_sequence_=preview_sequence_;
  }
#endif
}
}
