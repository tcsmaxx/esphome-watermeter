#include "camera_power.h"
#include "esp_camera.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
bool CameraPowerController::supported() const {auto *s=esp_camera_sensor_get();return s&&s->id.PID==OV5640_PID;}
void CameraPowerController::setup() {
  preference_=global_preferences->make_preference<CameraPowerSettings>(0x7a32b90a);
  CameraPowerSettings saved;if(preference_.load(&saved)&&saved.version==1&&saved.standby<=1&&saved.weak_drive<=1)settings_=saved;
  last_activity_=millis();status_=supported()?"Kamera aktiv":"Standby nur für OV5640 verfügbar";
  if(supported()){auto *s=esp_camera_sensor_get();original_drive_=s->get_reg(s,0x302c,0xc0);apply_drive_();}
}
bool CameraPowerController::set_sleep_(bool sleep) {
  auto *s=esp_camera_sensor_get();
  if(sleep)sleeping_=true; // Unconfirmed sleep must still be explicitly woken on demand.
  // Mask only software power-down. In particular, never set the reset bit.
  if(!s||s->set_reg(s,0x3008,0x40,sleep?0x40:0)!=0){failed_=true;status_="Standby-/Aufweckfehler; erneuter Versuch";return false;}
  const int value=s->get_reg(s,0x3008,0x40);
  if(value<0||bool(value&0x40)!=sleep){failed_=true;status_="Standby-Register nicht bestätigt";return false;}
  if(!sleep)++generation_;
  sleeping_=sleep;failed_=false;waking_=!sleep;wake_started_=millis();
  status_=sleep?"Sensor im Software-Standby":"Kamera wacht auf";
  ESP_LOGI("meter_power","%s",status_.c_str());return true;
}
bool CameraPowerController::apply_drive_() {
  if(!supported())return false;
  auto *s=esp_camera_sensor_get();if(original_drive_<0)original_drive_=s->get_reg(s,0x302c,0xc0);
  if(original_drive_<0){status_="Ausgangstreiber konnte nicht gelesen werden";return false;}
  const int desired=settings_.weak_drive?0:original_drive_;
  if(s->set_reg(s,0x302c,0xc0,desired)!=0||s->get_reg(s,0x302c,0xc0)!=desired){status_="Ausgangstreiber-Einstellung fehlgeschlagen";return false;}
  drive_applied_=true;return true;
}
void CameraPowerController::request() {
  last_activity_=millis();if(!supported()||!sleeping_)return;
  if(failed_&&millis()-last_attempt_<1000)return;
  last_attempt_=millis();set_sleep_(false);last_attempt_=millis();
}
bool CameraPowerController::ready() {
  if(!supported())return true;
  if(sleeping_)return false;
  if(waking_){if(millis()-wake_started_<300)return false;waking_=false;status_="Kamera aktiv";}
  return !failed_;
}
void CameraPowerController::loop(bool hold) {
  if(!supported())return;
  if(hold||!settings_.standby)request();
  ready();
  if(!sleeping_&&!drive_applied_&&millis()-drive_attempt_>=1000){drive_attempt_=millis();apply_drive_();drive_attempt_=millis();}
  if(!hold&&settings_.standby&&!sleeping_&&millis()-last_activity_>=5000&&(!failed_||millis()-last_attempt_>=1000)){
    last_attempt_=millis();set_sleep_(true);last_attempt_=millis();
  }
}
bool CameraPowerController::configure(bool standby,bool weak_drive) {
  CameraPowerSettings next;next.standby=standby;next.weak_drive=weak_drive;
  if(!preference_.save(&next)||!global_preferences->sync()){preference_.save(&settings_);global_preferences->sync();return false;}
  settings_=next;drive_applied_=false;request();return true;
}
}
