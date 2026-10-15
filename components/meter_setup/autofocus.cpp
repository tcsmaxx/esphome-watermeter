#include "autofocus.h"
#include "esp_camera.h"
#include "esp_camera_af.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
bool AutofocusController::supported() const {return esp_camera_af_is_supported(esp_camera_sensor_get());}
bool AutofocusController::start() {
  if(state()==RUNNING||state()==HUNG)return false;
  if(!supported()){state_=UNSUPPORTED;return false;}
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
  auto *sensor=esp_camera_sensor_get();esp_err_t result=ESP_OK;
  if(!self->initialized_){
    esp_camera_af_config_t config{};config.mode=ESP_CAMERA_AF_MODE_MANUAL;config.timeout_ms=2000;
    result=esp_camera_af_init(sensor,&config);self->initialized_=result==ESP_OK;
  }
  if(result==ESP_OK)result=esp_camera_af_trigger(sensor);
  esp_camera_af_status_t status{};
  if(result==ESP_OK){
    const uint32_t began=millis();
    do {
      result=esp_camera_af_get_status(sensor,&status);
      if(result!=ESP_OK||(status.focused&&!status.busy))break;
      vTaskDelay(pdMS_TO_TICKS(50));
    } while(millis()-began<4000);
    if(result==ESP_OK&&(!status.focused||status.busy))result=ESP_ERR_TIMEOUT;
  }
  self->error_=result;
  if(result==ESP_OK)ESP_LOGI("meter_autofocus","Einzelfokus erfolgreich");
  else ESP_LOGW("meter_autofocus","Autofokus fehlgeschlagen: %s, Status 0x%02x",esp_err_to_name(result),status.raw);
  int expected=RUNNING;self->state_.compare_exchange_strong(expected,result==ESP_OK?FOCUSED:FAILED);
  vTaskDelete(nullptr);
}
}
