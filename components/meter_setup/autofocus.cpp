#include "autofocus.h"
#include "esp_camera.h"
#include "esp_camera_af.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
bool AutofocusController::supported() const {return esp_camera_af_is_supported(esp_camera_sensor_get());}
bool AutofocusController::start() {return begin_(false,0);}
bool AutofocusController::start_manual(uint16_t position) {
  if(position>1023)return false;
  auto *s=esp_camera_sensor_get();if(!s||s->id.PID!=OV5640_PID)return false;
  return begin_(true,position);
}
bool AutofocusController::begin_(bool manual,uint16_t position) {
  if(state()==RUNNING||state()==HUNG)return false;
  if(!supported()){state_=UNSUPPORTED;return false;}
  manual_=manual;requested_position_=position;
  started_=millis();error_=0;state_=RUNNING;
  if(xTaskCreate(task_,"meter_af",5120,this,1,nullptr)!=pdPASS){error_=ESP_ERR_NO_MEM;state_=FAILED;return false;}
  return true;
}
AutofocusController::State AutofocusController::state() {
  int current=state_.load();
  if(current==RUNNING&&millis()-started_>15000){state_.compare_exchange_strong(current,HUNG);}
  return static_cast<State>(state_.load());
}
void AutofocusController::task_(void *context) {
  auto *self=static_cast<AutofocusController*>(context);
  auto *sensor=esp_camera_sensor_get();esp_err_t result=ESP_OK;esp_camera_af_status_t status{};
  if(self->reset_requested_.exchange(false))self->initialized_=false;
  if(self->manual_){
    // Hold only the AF MCU in reset. No sensor reset or AF firmware may move the lens.
    self->initialized_=false;self->position_=-1;
    const auto p=self->requested_position_;
    if(sensor->set_reg(sensor,0x3000,0x20,0x20)!=0 || sensor->get_reg(sensor,0x3000,0x20)!=0x20)result=ESP_FAIL;
    // OV5640 datasheet: D[3:0] in 3602[7:4], D[9:4] in 3603[5:0].
    // Preserve slew-rate and debug bits; clear VCM power-down (3603[7]).
    if(result==ESP_OK&&(sensor->set_reg(sensor,0x3602,0xf0,(p&15)<<4)!=0 || sensor->set_reg(sensor,0x3603,0xbf,p>>4)!=0))result=ESP_FAIL;
    if(result==ESP_OK){
      vTaskDelay(pdMS_TO_TICKS(100));
      if(sensor->get_reg(sensor,0x3602,0xf0)!=int((p&15)<<4)||sensor->get_reg(sensor,0x3603,0xbf)!=int(p>>4))result=ESP_FAIL;
      else self->position_=p;
    }
  } else {
  self->position_=-1;
  if(!self->initialized_){
    ESP_LOGI("meter_autofocus","Autofokus-Firmware wird initialisiert");
    esp_camera_af_config_t config{};config.mode=ESP_CAMERA_AF_MODE_MANUAL;config.timeout_ms=2000;
    result=esp_camera_af_init(sensor,&config);self->initialized_=result==ESP_OK;
  }
  if(result==ESP_OK)result=esp_camera_af_trigger(sensor);
  if(result==ESP_OK){
    const uint32_t began=millis();
    do {
      result=esp_camera_af_get_status(sensor,&status);
      if(result!=ESP_OK||(status.focused&&!status.busy))break;
      vTaskDelay(pdMS_TO_TICKS(50));
    } while(millis()-began<4000);
    if(result==ESP_OK&&(!status.focused||status.busy))result=ESP_ERR_TIMEOUT;
  }
  }
  if(result!=ESP_OK)self->initialized_=false; // Retry firmware initialization after a sensor/wake error.
  self->error_=result;
  if(result==ESP_OK)ESP_LOGI("meter_autofocus","%s",self->manual_?"Manuelle Fokusposition gesetzt":"Einzelfokus erfolgreich");
  else ESP_LOGW("meter_autofocus","Autofokus fehlgeschlagen: %s, Status 0x%02x",esp_err_to_name(result),status.raw);
  int expected=RUNNING;self->state_.compare_exchange_strong(expected,result==ESP_OK?FOCUSED:FAILED);
  vTaskDelete(nullptr);
}
}
