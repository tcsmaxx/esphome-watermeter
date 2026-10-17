#include "meter_setup.h"
#include <cstdlib>
#include <cstring>
#include "esphome/core/log.h"
namespace esphome::meter_setup {
bool MeterSetup::parse_options_(AsyncWebServerRequest *r,bool power) {
  auto number=[r](const char *key,uint32_t lo,uint32_t hi,uint32_t &out){
    if(!r->hasParam(key))return false;
    const std::string s=r->getParam(key)->value();
    if(s.empty()||s.size()>8||s.find_first_not_of("0123456789")!=std::string::npos)return false;
    out=std::strtoul(s.c_str(),nullptr,10);return out>=lo&&out<=hi;
  };
  uint32_t position,enabled,count,brightness,settle,standby=0,weak=0;
  if(!r->hasParam("focus_mode") || (r->getParam("focus_mode")->value()!="auto"&&r->getParam("focus_mode")->value()!="manual") ||
     !number("position",0,1023,position)||!number("enabled",0,1,enabled)||!number("led_count",1,(illumination_?led_capacity_():64),count)||
     !number("brightness",1,100,brightness)||!number("settle_ms",0,5000,settle)||
     (power&&(!number("standby",0,1,standby)||!number("weak_drive",0,1,weak)))){
    r->send(400,"text/plain; charset=utf-8","Fokus, Beleuchtung oder Stromspareinstellung ungültig");return false;
  }
  uint64_t mask=illumination_settings_.led_mask;
  if(r->hasParam("led_mask")&&!parse_led_mask(r->getParam("led_mask")->value(),mask)){r->send(400,"text/plain; charset=utf-8","LED-Auswahl ungültig");return false;}
  pending_manual_focus_=r->getParam("focus_mode")->value()=="manual";
  pending_autofocus_=!pending_manual_focus_;pending_focus_position_=position;
  pending_illumination_=illumination_settings_;pending_illumination_.enabled=enabled;pending_illumination_.led_count=count;
  pending_illumination_.led_mask=mask;pending_illumination_.brightness=brightness;pending_illumination_.settle_ms=settle;
  if(power){pending_standby_=standby;pending_weak_drive_=weak;}
  return true;
}
bool MeterSetup::save_all_() {
  ++save_attempt_;save_ok_=false;
  const bool layout_changed=settings_.digit_count!=pending_.digit_count||settings_.decimals!=pending_.decimals;
  const bool baseline_changed=settings_.baseline!=pending_.baseline||settings_.calibrated!=pending_.calibrated||settings_.digit_count!=pending_.digit_count||settings_.decimals!=pending_.decimals;
  auto options=runtime_;options.warning_after=pending_warning_after_;if(baseline_changed)options.last_valid_epoch=0;
  AutofocusSettings focus;focus.before_reading=pending_autofocus_;focus.manual_enabled=pending_manual_focus_;focus.position=pending_focus_position_;
  const bool old_standby=camera_power_.standby_enabled(),old_weak=camera_power_.weak_drive();
  const char *failure=nullptr;
  if(!save_configuration_(pending_,pending_alignment_,false))failure="Rahmen, Drehung und Referenzen";
  else if(!illumination_preference_.save(&pending_illumination_))failure="Beleuchtung";
  else if(!runtime_preference_.save(&options))failure="Ableseeinstellungen";
  else if(!autofocus_preference_.save(&focus))failure="Fokuseinstellungen";
  else if(!camera_power_.configure(pending_standby_,pending_weak_drive_))failure="Stromspareinstellungen / Flash-Synchronisierung";
  else if(!global_preferences->sync())failure="Flash-Synchronisierung";
  if(failure){
    save_configuration_(settings_,alignment_,false);illumination_preference_.save(&illumination_settings_);
    runtime_preference_.save(&runtime_);autofocus_preference_.save(&autofocus_settings_);
    camera_power_.configure(old_standby,old_weak);global_preferences->sync();
    message_=std::string("Speichern fehlgeschlagen: ")+failure+" · Änderungen bleiben ungespeichert";
    ESP_LOGE("meter_setup","%s",message_.c_str());return false;
  }
  settings_=pending_;alignment_=draft_alignment_=pending_alignment_;runtime_=options;autofocus_settings_=focus;
  illumination_settings_=pending_illumination_;
  if(layout_changed){if(confidence_sensor_)confidence_sensor_->publish_state(NAN);for(int i=0;i<MAX_DIGITS;i++)if(digit_sensors_[i])digit_sensors_[i]->publish_state(NAN);digits_.clear();confidence_digits_.clear();confidence_=0;for(auto &value:digit_confidences_)value=NAN;preview_.reset();preview_size_=0;inference_jpeg_.reset();inference_jpeg_size_=0;}

  if(baseline_changed){have_previous_reading_=false;runtime_.last_valid_epoch=0;if(change_)change_->publish_state(NAN);if(flow_)flow_->publish_state(NAN);}
  if(settings_.calibrated){
    std::string zones="[";for(int i=0;i<settings_.digit_count;i++){if(i)zones+=',';zones+='[';for(int j=0;j<4;j++){if(j)zones+=',';zones+=std::to_string(settings_.boxes[i][j]);}zones+=']';}zones+=']';reader_->set_crop_zones(zones);
  }else paused_=true;
  mqtt_discovered_=false;mqtt_discovery_index_=0;mqtt_state_at_=0;
  for(int i=settings_.digit_count;i<MAX_DIGITS;i++)if(digit_sensors_[i])digit_sensors_[i]->publish_state(NAN);
  next_=millis()+settings_.interval*1000;
  save_ok_=true;++config_revision_;build_export_();
  message_=settings_.calibrated?"Alle Einstellungen gespeichert":"Alle Einstellungen als Entwurf gespeichert · Ziffernrahmen und Zählerstand ergänzen";
  return true;
}
}
