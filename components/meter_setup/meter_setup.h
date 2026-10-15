#pragma once
#include <mutex>
#include <memory>
#include <cmath>
#include <ctime>
#include "timestamp_camera.h"
#include "autofocus.h"
#include "alignment.h"
#include "esphome/components/light/addressable_light_effect.h"
#include "esp_heap_caps.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/esp32_camera/esp32_camera.h"
#include "esphome/components/meter_reader_tflite/meter_reader_tflite.h"
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/sensor/sensor.h"
namespace esphome::meter_setup {
class AlignedMeterReader;
struct Settings {
  uint32_t version{1};
  uint16_t boxes[8][4]{};
  uint32_t baseline{0}, max_step{1000}, interval{60};
  uint8_t decimals{3}, calibrated{0};
};
struct Configuration {
  uint32_t version{1};
  Settings settings{};
  AlignmentReference alignment{};
};
struct AutofocusSettings {uint32_t version{2};uint8_t before_reading{1},manual_enabled{0};uint16_t position{512};};
struct RuntimeSettings {
  uint32_t version{1}, warning_after{300}, last_valid_epoch{0};
};
struct RecoveryRecord {
  uint32_t version{1}, automatic_restarts{0}, consecutive_timeouts{0}, frame{0}, free_heap{0}, free_psram{0}, uptime_ms{0};
  char timestamp[24]{}, phase[32]{}, reason[160]{}, reader_log[160]{}, alignment[96]{};
};
struct LegacyIlluminationSettings {
  uint32_t version{1};
  uint16_t settle_ms{1000};
  uint8_t enabled{0}, brightness{30};
};
struct IlluminationSettings {
  uint32_t version{2};
  uint16_t settle_ms{1000};
  uint8_t enabled{0}, brightness{30};
  uint16_t led_count{8};
};
class MeterSetup;
class CountedWhiteEffect : public light::AddressableLightEffect {
 public:
  explicit CountedWhiteEffect(MeterSetup *owner) : light::AddressableLightEffect("Zählerlicht"),owner_(owner) {}
  void start() override {initial_=true;}
  void apply(light::AddressableLight &it,const Color &color) override;
 protected:
  MeterSetup *owner_;
  bool initial_{true};
  uint16_t last_count_{0};
  float last_brightness_{-1};
  Color last_color_{};
};
class MeterSetup : public Component, public camera::CameraListener, public AsyncWebHandler {
 public:
  std::shared_ptr<camera::CameraImage> align_image_(const std::shared_ptr<camera::CameraImage> &image);
  void set_illumination(light::AddressableLightState *v) {illumination_=v;v->add_effects({&illumination_effect_});}
  CameraPowerController *get_camera_power(){return &camera_power_;}
  uint16_t get_active_led_count() const {return illumination_led_count_;}
  uint16_t led_capacity_() const;
  bool accepts_reader_frame_();
  void set_camera(esp32_camera::ESP32Camera *v) { camera_ = v; }
  void set_reader(meter_reader_tflite::MeterReaderTFLite *v) { reader_ = v;if(log_)reader_->set_main_logs(log_); }
  void set_log(text_sensor::TextSensor *v) { log_ = v;if(reader_)reader_->set_main_logs(log_); }
  void set_server(web_server_base::WebServerBase *v) { server_ = v; }
  void set_value(sensor::Sensor *v) { value_ = v; }
  void set_change(sensor::Sensor *v) { change_=v; }
  void set_flow(sensor::Sensor *v) { flow_=v; }
  void set_last_update(text_sensor::TextSensor *v) { last_update_=v; }
  void set_status(text_sensor::TextSensor *v) { status_sensor_=v; }
  void set_error(text_sensor::TextSensor *v) { error_sensor_=v; }
  void set_reading_age(sensor::Sensor *v){age_sensor_=v;}
  void set_stale(binary_sensor::BinarySensor *v){stale_sensor_=v;}
  void set_confidence(sensor::Sensor *v){confidence_sensor_=v;}
  void set_digit_confidence(int i,sensor::Sensor *v){digit_sensors_[i]=v;}
  void capture_digit_scores_(const std::string &digits,const float *values);
  void capture_digit_log_(const char *tag,const char *message,size_t len);
  void set_problem(binary_sensor::BinarySensor *v) { problem_=v; }
  void setup() override;
  void loop() override;
  float get_setup_priority() const override { return setup_priority::LATE - 1; }
  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
 protected:
  bool save_configuration_(const Settings &settings,const AlignmentReference &alignment,bool flush);
  bool capture_references_();
  void begin_capture_(bool inference);
  bool parse_options_(AsyncWebServerRequest *request,bool power);
  bool save_all_();
  static bool valid_draft_(const Settings &settings);
  bool preview_active_{false},focus_only_{false},live_preview_{false};
  AutofocusSettings preview_focus_{};
  uint32_t save_attempt_{0};bool save_ok_{false};
  void autofocus_setup_();
  bool start_autofocus_();
  void autofocus_loop_();
  void autofocus_failed_(const char *reason);
  CameraPowerController camera_power_;
  uint32_t autofocus_power_generation_{UINT32_MAX};
  bool pending_standby_{true},pending_weak_drive_{false};
  AutofocusController autofocus_;
  AutofocusSettings autofocus_settings_{};
  ESPPreferenceObject autofocus_preference_;
  bool autofocus_once_{false},autofocus_used_{false},pending_autofocus_{true};
  bool manual_focus_once_{false},focus_job_manual_{false},pending_manual_focus_{false};
  uint16_t manual_focus_position_{512},pending_focus_position_{512};
  std::string autofocus_status_{"Noch nicht fokussiert"};
  void illumination_loop_();
  void set_illumination_(bool on,const IlluminationSettings &settings);
  bool save_illumination_(const IlluminationSettings &settings);
  void reset_illumination_();
  void start_(bool test);
  void reset_();
  void diagnostics_();
  void features_setup_();
  void features_loop_();
  void build_export_();
  void import_config_();
  void mqtt_loop_();
  RuntimeSettings runtime_{};
  ESPPreferenceObject runtime_preference_;
  sensor::Sensor *age_sensor_{},*confidence_sensor_{},*digit_sensors_[8]{};
  binary_sensor::BinarySensor *stale_sensor_{};
  float digit_confidences_[8]{};
  std::string confidence_digits_,export_json_,pending_import_;
  uint32_t pending_warning_after_{0},config_revision_{0},health_updated_{0},boot_started_{0},mqtt_image_sequence_{0};
  float reading_age_{NAN};
  bool stale_{false},mqtt_discovered_{false},confidence_pending_{false};
  uint32_t confidence_finished_at_{0},mqtt_state_at_{0};
  uint8_t mqtt_discovery_index_{0};
  std::shared_ptr<uint8_t> inference_jpeg_;
  size_t inference_jpeg_size_{0};
  std::time_t inference_capture_epoch_{0};
  uint32_t timestamped_sequence_{0};
  void set_preview_(const std::shared_ptr<uint8_t> &data,size_t size,bool rgb);
  std::shared_ptr<uint8_t> preview_;
  size_t preview_size_{0};
  bool preview_rgb_{false};
  uint32_t preview_sequence_{0};
  std::string preview_boxes_,preview_references_;
  void record_fault_(const std::string &reason,bool automatic_restart);
  void recovery_loop_();
  std::string reader_phase_() const;
  RecoveryRecord recovery_{};
  ESPPreferenceObject recovery_preference_;
  uint32_t reboot_at_{0}, recovery_delay_ms_{10000}, fault_saved_at_{0};
  bool reboot_pending_{false};
  std::string last_reader_log_;
  void result_(const std::string &s);
  std::string status_();
  static int invalid_box_(const Settings &s);
  static bool valid_(const Settings &s);
  esp32_camera::ESP32Camera *camera_{};
  meter_reader_tflite::MeterReaderTFLite *reader_{};
  text_sensor::TextSensor *log_{};
  web_server_base::WebServerBase *server_{};
  sensor::Sensor *value_{}, *change_{}, *flow_{};
  text_sensor::TextSensor *last_update_{}, *status_sensor_{}, *error_sensor_{};
  binary_sensor::BinarySensor *problem_{};
  uint32_t last_accepted_at_{0};
  bool have_previous_reading_{false}, reading_problem_{false};
  std::string diagnostic_status_, diagnostic_error_{"__initial__"}, reading_error_;
  light::AddressableLightState *illumination_{nullptr};
  CountedWhiteEffect illumination_effect_{this};
  uint16_t illumination_led_count_{8};
  ESPPreferenceObject illumination_preference_;
  IlluminationSettings illumination_settings_{},pending_illumination_{};
  bool capture_pending_{false}, capture_inference_{false}, flush_received_{false}, inference_started_{false};
  uint8_t capture_stage_{0};
  uint32_t capture_deadline_{0}, capture_started_{0}, light_test_deadline_{0};
  bool light_test_{false},illumination_on_{false};
  ESPPreferenceObject preference_;
  Settings settings_{}, pending_{};
  AlignmentReference alignment_{}, draft_alignment_{}, pending_alignment_{}, active_alignment_{};
  std::shared_ptr<uint8_t> displayed_jpeg_, reference_capture_;
  size_t displayed_size_{0}, reference_capture_size_{0};
  uint32_t displayed_frame_{0}, reference_revision_{0}, alignment_ms_{0};
  AlignmentMatch alignment_matches_[2]{};
  std::string alignment_result_{"Ausgeschaltet"};
  void update_status_();
  void stop_live_();
  void live_loop_(bool start,bool stop);
  bool live_{false},live_streaming_{false},live_was_paused_{true};
  uint32_t live_deadline_{0},live_last_frame_{0},live_frame_at_{0};
  std::mutex mutex_,status_mutex_;
  std::shared_ptr<uint8_t> jpeg_;
  size_t jpeg_size_{0};
  std::string message_{"Noch nicht eingerichtet"};
  std::string status_json_, http_task_name_;
  uint32_t status_updated_{0}, http_stack_free_{0};
  std::string digits_;
  uint32_t frame_{0}, next_{0}, started_{0}, reset_count_{0};
  float confidence_{0};
  bool busy_{false}, test_{false}, timed_out_{false}, accepted_{false};
  enum Command { NONE, CAPTURE, SAVE, TEST, PAUSE, RESUME, RESET, REFERENCE, LIGHT_ON, LIGHT_OFF, LIGHT_SAVE, RESTART, IMPORT, FOCUS, FOCUS_SAVE, POWER_SAVE, LIVE_START, LIVE_STOP, MANUAL_FOCUS, FOCUS_ONLY, PREVIEW, SAVE_ALL } command_{NONE};
  bool paused_{true};
};
class AlignedMeterReader : public meter_reader_tflite::MeterReaderTFLite {
 public:
  void loop() override;
  void arm_for_capture() {
    std::lock_guard<std::mutex> lock(frame_mutex_);
    pending_frame_.reset();frame_state_.store(FrameState::IDLE);
  }
  const char *phase() const {
    switch(frame_state_.load()) {
      case FrameState::IDLE:return "idle";
      case FrameState::REQUESTED:return "waiting_frame";
      case FrameState::AVAILABLE:return "frame_available";
      case FrameState::PROCESSING:return "processing";
      case FrameState::TIMEOUT:return "frame_timeout";
    }
    return "unknown";
  }
  void set_alignment_owner(MeterSetup *owner) {owner_=owner;}
  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;
 protected:
  MeterSetup *owner_{nullptr};
};
}
