#include "meter_setup.h"
#include "web_ui.h"
#include "reading_guard.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <ctime>
#include "esp_jpeg_dec.h"
namespace esphome::meter_setup {
void CountedWhiteEffect::apply(light::AddressableLight &it,const Color &color) {
  const auto count=owner_->get_active_led_count();
  const float brightness=this->state_->current_values.get_brightness();
  if(!initial_ && count==last_count_ && brightness==last_brightness_ && last_color_==color) return;
  for(int i=0;i<it.size();i++) it[i]=i<count?color:Color(0,0,0,0);
  it.schedule_show();initial_=false;last_count_=count;last_brightness_=brightness;last_color_=color;
}
static std::string zones(const Settings &s);
using ImageBuffer=std::shared_ptr<uint8_t>;
static ImageBuffer decode_rgb(const uint8_t *data,size_t len) {
  if(!data || len<4) return {};
  jpeg_dec_config_t config=DEFAULT_JPEG_DEC_CONFIG();
  config.output_type=JPEG_PIXEL_FORMAT_RGB888;
  config.scale.width=config.clipper.width=640;config.scale.height=config.clipper.height=480;
  config.block_enable=false;
  jpeg_dec_handle_t decoder=nullptr;
  if(jpeg_dec_open(&config,&decoder)!=JPEG_ERR_OK) return {};
  auto *buffer=static_cast<uint8_t *>(heap_caps_aligned_alloc(16,640*480*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  ImageBuffer rgb(buffer,heap_caps_free);
  if(!rgb) {jpeg_dec_close(decoder);return {};}
  jpeg_dec_io_t io{};io.inbuf=const_cast<uint8_t *>(data);io.inbuf_len=io.inbuf_remain=len;
  io.outbuf=rgb.get();io.out_size=640*480*3;
  jpeg_dec_header_info_t header{};
  bool ok=jpeg_dec_parse_header(decoder,&io,&header)==JPEG_ERR_OK;
  ok=ok && header.width==640 && header.height==480;
  if(ok) ok=jpeg_dec_process(decoder,&io)==JPEG_ERR_OK;
  jpeg_dec_close(decoder);return ok?rgb:ImageBuffer{};
}
static ImageBuffer grayscale(const ImageBuffer &rgb) {
  if(!rgb) return {};
  auto *buffer=static_cast<uint8_t *>(heap_caps_malloc(640*480,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  ImageBuffer gray(buffer,heap_caps_free);if(!gray) return {};
  for(int i=0;i<640*480;i++) gray.get()[i]=(77*rgb.get()[i*3]+150*rgb.get()[i*3+1]+29*rgb.get()[i*3+2])>>8;
  return gray;
}
class AlignedImage : public camera::CameraImage {
 public:
  AlignedImage(ImageBuffer rgb,const std::shared_ptr<camera::CameraImage> &source):rgb_(std::move(rgb)) {
    for(int i=0;i<3;i++) requested_[i]=source->was_requested_by(static_cast<camera::CameraRequester>(i));
  }
  uint8_t *get_data_buffer() override {return rgb_.get();}
  size_t get_data_length() override {return 640*480*3;}
  bool was_requested_by(camera::CameraRequester r) const override {return int(r)<3 && requested_[int(r)];}
 protected:
  ImageBuffer rgb_;bool requested_[3]{};
};
void AlignedMeterReader::on_camera_image(const std::shared_ptr<camera::CameraImage> &image) {
  if(owner_ && !owner_->accepts_reader_frame_()) return;
  if(frame_state_.load()!=FrameState::REQUESTED) return;
  auto processed=owner_?owner_->align_image_(image):image;
  if(!processed) {std::lock_guard<std::mutex> lock(frame_mutex_);frame_state_.store(FrameState::IDLE);pending_frame_.reset();return;}
  meter_reader_tflite::MeterReaderTFLite::on_camera_image(processed);
}
std::shared_ptr<camera::CameraImage> MeterSetup::align_image_(const std::shared_ptr<camera::CameraImage> &image) {
  std::lock_guard<std::mutex> lock(mutex_);
  preview_.reset();preview_size_=0;++preview_sequence_;
  inference_jpeg_.reset();inference_jpeg_size_=0;
  inference_capture_epoch_=camera_capture_epoch(image);
  const auto original_size=image->get_data_length();
  auto original=ImageBuffer(static_cast<uint8_t*>(heap_caps_malloc(original_size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),heap_caps_free);
  if(original){std::memcpy(original.get(),image->get_data_buffer(),original_size);inference_jpeg_=original;inference_jpeg_size_=original_size;}
  if(!busy_ || !active_alignment_.enabled) {
    alignment_result_="Ausgeschaltet";alignment_ms_=0;
    if(inference_jpeg_)set_preview_(inference_jpeg_,inference_jpeg_size_,false);
    return image;
  }
  const uint32_t begin=millis();
  std::string error;
  auto rgb=decode_rgb(image->get_data_buffer(),image->get_data_length());
  auto gray=grayscale(rgb);
  if(!gray) error="Kamerabild konnte nicht dekodiert werden";
  else {
    alignment_matches_[0]=match_reference(gray.get(),active_alignment_,0);
    alignment_matches_[1]=match_reference(gray.get(),active_alignment_,1);
    if(!alignment_matches_[0].valid || !alignment_matches_[1].valid) error="Referenzen fehlen oder sind nicht eindeutig";
  }
  auto transform=alignment_transform(active_alignment_,alignment_matches_[0],alignment_matches_[1]);
  if(error.empty() && !transform.valid) error="Drehung/Abstand der Referenzen außerhalb der Grenzen";
  const auto &boxes=test_?pending_.boxes:settings_.boxes;
  if(error.empty()) for(const auto &box:boxes) if(!alignment_covers_box(transform,box)) {error="Ziffernrahmen liegt nach Ausrichtung außerhalb des Bildes";break;}
  ImageBuffer corrected;
  if(error.empty()) {
    auto *data=static_cast<uint8_t *>(heap_caps_malloc(640*480*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    corrected=ImageBuffer(data,heap_caps_free);
    if(!corrected || !warp_rgb(rgb.get(),corrected.get(),transform)) error="Nicht genug Speicher für Bildausrichtung";
  }
  alignment_ms_=millis()-begin;
  if(!error.empty()) {
    alignment_result_=error;message_="Ausrichtungsfehler: "+error;
    if(!test_) {reading_problem_=true;reading_error_=message_;}
    inference_started_=false;set_illumination_(light_test_,pending_illumination_);
    busy_=false;accepted_=false;next_=millis()+settings_.interval*1000;reader_->set_pause_processing(true);
    if(test_ && settings_.calibrated) reader_->set_crop_zones(zones(settings_));
    ESP_LOGW("meter_setup","%s",message_.c_str());return {};
  }
  alignment_result_="OK";
  ESP_LOGI("meter_setup","Bild ausgerichtet in %u ms, Referenzen %u / %u Prozent",alignment_ms_,unsigned(alignment_matches_[0].score*100),unsigned(alignment_matches_[1].score*100));
  // The upstream RGB/JPEG autodetector only looks for the JPEG SOI prefix.
  // Raw RGB is known here; neutralize that accidental prefix at the far corner.
  if(corrected.get()[0]==0xff && corrected.get()[1]==0xd8) corrected.get()[0]=0xfe;
  set_preview_(corrected,640*480*3,true);
  return std::make_shared<AlignedImage>(std::move(corrected),image);
}
bool MeterSetup::save_configuration_(const Settings &settings,const AlignmentReference &alignment,bool flush) {
  Configuration next;next.settings=settings;next.alignment=alignment;
  if(!preference_.save(&next) || (flush && !global_preferences->sync())) {
    Configuration previous;previous.settings=settings_;previous.alignment=alignment_;preference_.save(&previous);return false;
  }
  return true;
}
bool MeterSetup::capture_references_() {
  auto rgb=decode_rgb(reference_capture_.get(),reference_capture_size_);
  auto gray=grayscale(rgb);reference_capture_.reset();reference_capture_size_=0;
  auto draft=pending_alignment_;draft.ready=0;
  if(!gray || !capture_reference(gray.get(),draft)) {draft_alignment_=draft;message_="Referenzen ungeeignet: feste, kontrastreiche Bereiche wählen";return false;}
  draft_alignment_=draft;++reference_revision_;message_="Referenzen vorbereitet; mit Speichern dauerhaft sichern";return true;
}
static std::string quote(const std::string &s) {
  std::string out = "\"";
  for (unsigned char c : s) { if (c == '"' || c == '\\') out += '\\'; if(c >= 32) out += c; }
  return out + '"';
}
int MeterSetup::invalid_box_(const Settings &s) {
  for(int i=0;i<8;i++) {
    const auto &b=s.boxes[i];
    if(b[0]>=b[2] || b[1]>=b[3] || b[2]>640 || b[3]>480) return i;
    // Compare centers: small overlaps are valid when tuning individual crops.
    if(i && b[0]+b[2]<=s.boxes[i-1][0]+s.boxes[i-1][2]) return i;
  }
  return -1;
}
bool MeterSetup::valid_(const Settings &s) {
  return s.version==1 && s.decimals<=6 && s.interval>=10 && s.interval<=86400 &&
    s.baseline<=99999999 && s.max_step>=1 && s.max_step<=99999999 && invalid_box_(s)<0;
}
static std::string zones(const Settings &s) {
  std::string out="["; char b[64];
  for(int i=0;i<8;i++){snprintf(b,sizeof(b),"%s[%u,%u,%u,%u]",i?",":"",s.boxes[i][0],s.boxes[i][1],s.boxes[i][2],s.boxes[i][3]);out+=b;}
  return out+"]";
}
void MeterSetup::setup() {
  reader_->stop_poller(); reader_->set_pause_processing(true);
  preference_=global_preferences->make_preference<Configuration>(0x7a32b903);
  Configuration loaded;
  const bool have_new=preference_.load(&loaded);
  if(have_new && loaded.version==1 && loaded.settings.calibrated && valid_(loaded.settings)) {
    settings_=loaded.settings;alignment_=loaded.alignment;
    if(alignment_.enabled && (!alignment_.ready || !valid_reference_regions(alignment_))) {paused_=true;reading_problem_=true;reading_error_="Ausrichtungsreferenzen ungültig; neu einrichten";message_=reading_error_;}
    else {paused_=false;message_="Konfiguration geladen";}
    reader_->set_crop_zones(zones(settings_));
  } else if(!have_new) {
    auto legacy=global_preferences->make_preference<Settings>(0x7a32b901);Settings previous;
    if(legacy.load(&previous) && previous.calibrated && valid_(previous)) {
      settings_=previous;paused_=false;message_="Vorhandene Konfiguration übernommen";
      reader_->set_crop_zones(zones(settings_));save_configuration_(settings_,alignment_,true);
    }
  }
  draft_alignment_=alignment_;
  illumination_preference_=global_preferences->make_preference<IlluminationSettings>(0x7a32b906);
  IlluminationSettings saved_light;
  const bool have_light=illumination_preference_.load(&saved_light);
  const auto valid_light=[this](const IlluminationSettings &v) {
    return v.version==2 && v.enabled<=1 && v.brightness>=1 && v.brightness<=100 && v.settle_ms<=5000 && v.led_count>=1 && v.led_count<=led_capacity_();
  };
  if(have_light && valid_light(saved_light)) illumination_settings_=saved_light;
  else if(!have_light) {
    auto legacy=global_preferences->make_preference<LegacyIlluminationSettings>(0x7a32b904);
    LegacyIlluminationSettings old;
    if(legacy.load(&old) && old.version==1) {
      saved_light.enabled=old.enabled;saved_light.brightness=old.brightness;saved_light.settle_ms=old.settle_ms;
      saved_light.led_count=std::max<uint16_t>(1,std::min<uint16_t>(8,led_capacity_()));
      if(valid_light(saved_light)) save_illumination_(saved_light);
    }
  }
  illumination_settings_.led_count=std::max<uint16_t>(1,std::min<uint16_t>(illumination_settings_.led_count,led_capacity_()));
  pending_illumination_=illumination_settings_;set_illumination_(false,illumination_settings_);
  camera_->add_listener(this);
  // Finish on a fresh loop iteration, outside the reader's nested publish stack.
  log_->add_on_state_callback([this](const std::string &s){
    this->defer("meter_result", [this, s](){result_(s);});
  });
  recovery_preference_=global_preferences->make_preference<RecoveryRecord>(0x7a32b907);
  RecoveryRecord previous_fault;
  if(recovery_preference_.load(&previous_fault) && previous_fault.version==1) {
    recovery_=previous_fault;
    recovery_.timestamp[sizeof(recovery_.timestamp)-1]=0;recovery_.phase[sizeof(recovery_.phase)-1]=0;recovery_.reason[sizeof(recovery_.reason)-1]=0;
    recovery_.reader_log[sizeof(recovery_.reader_log)-1]=0;recovery_.alignment[sizeof(recovery_.alignment)-1]=0;
    if(recovery_.reason[0]) ESP_LOGW("meter_setup","Letzter Fehler: %s; Phase: %s; Reader: %s",recovery_.reason,recovery_.phase,recovery_.reader_log);
    if(recovery_.consecutive_timeouts) recovery_delay_ms_=std::min<uint32_t>(1800000,60000U << std::min<uint32_t>(5,recovery_.consecutive_timeouts-1));
  }
  next_=millis()+recovery_delay_ms_;
  status_json_=status_();
  autofocus_setup_();
  features_setup_();
  server_->add_handler(this);
  ESP_LOGI("meter_setup", "Loop task %s, configured stack %u bytes", pcTaskGetName(nullptr), ESPHOME_LOOP_TASK_STACK_SIZE);
}
void MeterSetup::on_camera_image(const std::shared_ptr<camera::CameraImage> &image) {
  {
    std::lock_guard<std::mutex> guard(mutex_);
    if(capture_pending_ && capture_stage_!=2) {if(capture_stage_==1) flush_received_=true;return;}
  }
  const size_t len=image->get_data_length();
  if(len>160000) return;
  auto *data=static_cast<uint8_t *>(heap_caps_malloc(len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if(!data) return;
  std::memcpy(data,image->get_data_buffer(),len);
  std::shared_ptr<uint8_t> copy(data,heap_caps_free);
  std::lock_guard<std::mutex> guard(mutex_);
  jpeg_=std::move(copy); jpeg_size_=len; ++frame_;
  if(capture_pending_ && capture_stage_==2 && !capture_inference_) {
    capture_pending_=false;set_illumination_(light_test_,pending_illumination_);message_="Kamerabild aufgenommen";
  }
}
void MeterSetup::reset_() {
  preview_.reset();preview_size_=0;++preview_sequence_;
  Settings cleared;
  if(!save_configuration_(cleared,AlignmentReference{},true)) {
    message_="Löschen fehlgeschlagen";
    return;
  }
  settings_=cleared; pending_=cleared;
  alignment_=draft_alignment_=pending_alignment_=active_alignment_=AlignmentReference{};
  reference_capture_.reset();alignment_result_="Ausgeschaltet";alignment_ms_=0;
  paused_=true; accepted_=false; test_=false;
  reader_->set_pause_processing(true);
  reader_->set_crop_zones("[]");
  digits_.clear(); confidence_=0;
  value_->publish_state(NAN);
  have_previous_reading_=false; reading_problem_=false; reading_error_.clear();
  if(change_) change_->publish_state(NAN);
  if(flow_) flow_->publish_state(NAN);
  if(last_update_) last_update_->publish_state("Noch keine Ablesung");
  ++reset_count_;
  message_="Zählerkonfiguration gelöscht";reset_illumination_();
}
uint16_t MeterSetup::led_capacity_() const {
  if(!illumination_) return 64;
  const auto *output=static_cast<light::AddressableLight *>(illumination_->get_output());
  return uint16_t(std::max<int32_t>(0,std::min<int32_t>(64,output->size())));
}
bool MeterSetup::accepts_reader_frame_() {
  std::lock_guard<std::mutex> lock(mutex_);
  return busy_ && inference_started_ && !capture_pending_;
}
void MeterSetup::set_illumination_(bool on,const IlluminationSettings &settings) {
  if(!illumination_) return;
  auto call=illumination_->make_call();
  illumination_led_count_=settings.led_count;
  call.set_save(false).set_state(on);
  // An explicit transition conflicts with an effect, even at zero milliseconds.
  // Turning off without an explicit effect lets LightCall stop the active effect.
  if(on) call.set_effect("Zählerlicht").set_color_mode(light::ColorMode::RGB_WHITE).set_rgbw(0,0,0,1).set_brightness(settings.brightness/100.0f);
  else call.set_transition_length(0);
  call.perform();illumination_on_=on;
}
bool MeterSetup::save_illumination_(const IlluminationSettings &settings) {
  if(!illumination_preference_.save(&settings) || !global_preferences->sync()) {
    illumination_preference_.save(&illumination_settings_);return false;
  }
  illumination_settings_=settings;return true;
}
void MeterSetup::reset_illumination_() {
  light_test_=false;capture_pending_=false;inference_started_=false;
  set_illumination_(false,illumination_settings_);
  IlluminationSettings defaults;defaults.led_count=std::max<uint16_t>(1,std::min<uint16_t>(8,led_capacity_()));
  if(!save_illumination_(defaults)) message_="Zähler gelöscht; LED-Einstellungen konnten nicht gelöscht werden";
  pending_illumination_=illumination_settings_;
}
void MeterSetup::begin_capture_(bool inference) {
  autofocus_used_=false;
  capture_inference_=inference;capture_started_=millis();inference_started_=false;
  capture_pending_=true;flush_received_=false;
  const bool automatic_light=illumination_ && (illumination_settings_.enabled || light_test_);
  const auto &lighting=light_test_?pending_illumination_:illumination_settings_;
  if(automatic_light) {
    set_illumination_(true,lighting);
    capture_stage_=0;capture_deadline_=millis()+lighting.settle_ms;
  } else if(autofocus_once_||(inference&&autofocus_settings_.before_reading&&autofocus_.supported())) {
    capture_stage_=0;capture_deadline_=millis();
  } else {
    capture_stage_=2;
    if(inference) {
      capture_pending_=false;inference_started_=true;
      static_cast<AlignedMeterReader *>(reader_)->arm_for_capture();
      reader_->set_pause_processing(false);reader_->update();
    }
    camera_->request_image(camera::WEB_REQUESTER);
  }
}
void MeterSetup::illumination_loop_() {
  autofocus_loop_();
  if(light_test_ && int32_t(millis()-light_test_deadline_)>=0) {
    light_test_=false;if(!busy_ && !capture_pending_)set_illumination_(false,illumination_settings_);
  }
  if(!capture_pending_) return;
  if(millis()-capture_started_>(autofocus_used_?25000U:15000U)) {
    capture_pending_=false;busy_=false;inference_started_=false;reader_->set_pause_processing(true);
    set_illumination_(light_test_,pending_illumination_);message_="Kamerabild ausgeblieben";
    if(capture_inference_ && !test_) {reading_problem_=true;reading_error_=message_;}
    next_=millis()+settings_.interval*1000;return;
  }
  if(capture_stage_==0 && int32_t(millis()-capture_deadline_)>=0) {
    if(start_autofocus_())return;
    capture_stage_=1;camera_->request_image(camera::WEB_REQUESTER);
  } else if(capture_stage_==1 && flush_received_) {
    capture_stage_=2;
    if(capture_inference_) {
      capture_pending_=false;inference_started_=true;
      static_cast<AlignedMeterReader *>(reader_)->arm_for_capture();
      reader_->set_pause_processing(false);reader_->update();
    }
    camera_->request_image(camera::WEB_REQUESTER);
  }
}
void MeterSetup::start_(bool test) {
  confidence_pending_=false;confidence_digits_.clear();for(auto &v:digit_confidences_)v=NAN;
  active_alignment_=test?pending_alignment_:alignment_;
  busy_=true; test_=test; started_=millis(); accepted_=false;
  message_=test?"Test läuft …":"Ablesung läuft …";
  begin_capture_(true);
}
void MeterSetup::loop() {
  std::lock_guard<std::mutex> guard(mutex_);
  Command cmd=command_; command_=NONE;
  if(cmd==RESTART && !reboot_pending_) {
    record_fault_("Manueller Neustart über Setup",false);
    reboot_pending_=true;reboot_at_=millis()+1500;paused_=true;
    set_illumination_(false,illumination_settings_);message_="Gerät wird neu gestartet …";
  }
  recovery_loop_();
  if(reboot_pending_) {diagnostics_();if(millis()-status_updated_>=250){status_json_=status_();status_updated_=millis();}return;}
  if(cmd==FOCUS_SAVE) {
    const auto old=autofocus_settings_;autofocus_settings_.before_reading=pending_autofocus_;
    if(autofocus_preference_.save(&autofocus_settings_)&&global_preferences->sync()){message_="Fokuseinstellung gespeichert";build_export_();}
    else {autofocus_settings_=old;autofocus_preference_.save(&old);global_preferences->sync();message_="Fokuseinstellung konnte nicht gespeichert werden";}
  }
  if(cmd==FOCUS){paused_=true;autofocus_once_=true;message_="Autofokus wird vorbereitet …";begin_capture_(false);}
  if(cmd==IMPORT && !busy_)import_config_();
  if(cmd==RESET && !busy_) {autofocus_settings_=AutofocusSettings{};autofocus_preference_.save(&autofocus_settings_);reset_();runtime_.last_valid_epoch=0;runtime_.warning_after=300;runtime_preference_.save(&runtime_);global_preferences->sync();build_export_();}
  if(cmd==REFERENCE && !busy_) capture_references_();
  if(cmd==CAPTURE) {message_="Kamerabild wird aufgenommen …";begin_capture_(false);}
  if(cmd==LIGHT_SAVE) {
    if(save_illumination_(pending_illumination_)) {message_="Beleuchtung gespeichert";build_export_();if(light_test_)set_illumination_(true,illumination_settings_);}
    else message_="Beleuchtung konnte nicht gespeichert werden";
  }
  if(cmd==LIGHT_ON) {light_test_=true;light_test_deadline_=millis()+120000;set_illumination_(true,pending_illumination_);message_="Lichttest eingeschaltet (maximal 2 Minuten)";}
  if(cmd==LIGHT_OFF) {light_test_=false;set_illumination_(false,illumination_settings_);message_="Licht ausgeschaltet";}
  illumination_loop_();
  if(cmd==PAUSE) { paused_=true; message_="Automatische Ablesung pausiert"; }
  if(cmd==RESUME && settings_.calibrated) { paused_=false; next_=millis(); }
  if((cmd==SAVE || cmd==TEST) && !busy_) {
    if(cmd==SAVE) {
      const auto previous_runtime=runtime_;
      pending_.calibrated=1;
      if(!save_configuration_(pending_,pending_alignment_,true)) {
        message_="Speichern fehlgeschlagen";paused_=true;return;
      }
      if(pending_warning_after_)runtime_.warning_after=pending_warning_after_;
      settings_=pending_;alignment_=draft_alignment_=pending_alignment_; have_previous_reading_=false;runtime_.last_valid_epoch=0;
      const bool runtime_saved=runtime_preference_.save(&runtime_)&&global_preferences->sync();
      if(!runtime_saved){runtime_=previous_runtime;runtime_preference_.save(&runtime_);global_preferences->sync();}
      build_export_();
      if(change_) change_->publish_state(NAN);
      if(flow_) flow_->publish_state(NAN);
      reader_->set_crop_zones(zones(settings_)); paused_=false; next_=millis()+1000; message_=runtime_saved?"Gespeichert":"Zähler gespeichert; Warnschwelle konnte nicht gespeichert werden";
    } else {
      reader_->set_crop_zones(zones(pending_)); start_(true);
    }
  }
  if(busy_ && !timed_out_ && millis()-started_>60000) {
    timed_out_=true; paused_=true; reading_problem_=true; reading_error_="Zeitüberschreitung bei Ablesung"; message_="Zeitüberschreitung: automatischer Neustart in 5 Sekunden";
    record_fault_("Kein Ableseergebnis innerhalb von 60 Sekunden",true);
    reboot_pending_=true;reboot_at_=millis()+5000;
    set_illumination_(false,illumination_settings_);
    reader_->set_pause_processing(true); // Keep busy latched: no ROI changes while a worker could still be alive.
  }
  if(!busy_ && !capture_pending_ && !light_test_ && !paused_ && settings_.calibrated && int32_t(millis()-next_)>=0) start_(false);
  features_loop_();
  diagnostics_();
  if(millis()-status_updated_>=250) {
    status_json_=status_();
    status_updated_=millis();
  }
}
void MeterSetup::result_(const std::string &s) {
  // Reader publishes callbacks from its main loop, never the inference task.
  std::lock_guard<std::mutex> guard(mutex_);
  last_reader_log_=s.substr(0,159);
  if(!busy_) return;
  if(s.rfind("CRITICAL: Camera Frame Failure",0)==0 && !timed_out_) {
    record_fault_(s,false);
    reader_->set_pause_processing(true);
    static_cast<AlignedMeterReader *>(reader_)->arm_for_capture();
    busy_=false;inference_started_=false;accepted_=false;
    set_illumination_(light_test_,pending_illumination_);
    message_="Kamerabild ausgeblieben; erneuter Versuch geplant";
    if(!test_) {reading_problem_=true;reading_error_=s;}
    if(test_ && settings_.calibrated)reader_->set_crop_zones(zones(settings_));
    next_=millis()+settings_.interval*1000;return;
  }
  if(s.rfind("Reading: ",0)!=0) return;
  reader_->set_pause_processing(true);inference_started_=false;
  set_illumination_(light_test_,pending_illumination_);
  uint32_t raw=0;
  bool ok=parse_reading(s,digits_,confidence_,raw);
  if(timed_out_) { message_="Verspätetes Ergebnis verworfen; bitte neu starten"; return; }
  confidence_finished_at_=millis();confidence_pending_=confidence_digits_!=digits_;
  if(confidence_sensor_)confidence_sensor_->publish_state(confidence_);
  for(int i=0;i<8;i++)if(digit_sensors_[i])digit_sensors_[i]->publish_state(confidence_digits_==digits_?digit_confidences_[i]:NAN);
  if(test_) message_=ok?"Test erkannt; noch nicht an Home Assistant übertragen":"Test unsicher; Rahmen/Beleuchtung prüfen";
  else {
    if(!ok) message_="Abgewiesen: KI-Erkennung unsicher oder ungültig";
    else if(raw<settings_.baseline) {ok=false;message_="Abgewiesen: Stand kleiner als gespeicherter Stand";}
    else if(!within_range(raw,settings_.baseline,settings_.max_step)) {ok=false;message_="Abgewiesen: Sprung zu groß; aktuellen Stand von Hand prüfen";}
    accepted_=ok;
    reading_problem_=!ok;
    reading_error_=ok?"":message_;
    if(ok) {
      const auto epoch=std::time(nullptr);runtime_.last_valid_epoch=epoch>1577836800?uint32_t(epoch):0;runtime_preference_.save(&runtime_);
      if(recovery_.consecutive_timeouts) {
        recovery_.consecutive_timeouts=0;recovery_preference_.save(&recovery_);global_preferences->sync();
      }
      const float divisor=std::pow(10.0f,settings_.decimals);
      const float delta=(raw-settings_.baseline)/divisor;
      const uint32_t now=millis(), elapsed=now-last_accepted_at_;
      if(change_) change_->publish_state(delta);
      if(flow_) flow_->publish_state(have_previous_reading_ && elapsed?delta*3600000.0f/elapsed:NAN);
      last_accepted_at_=now; have_previous_reading_=true;
      if(last_update_) {
        const std::time_t epoch=std::time(nullptr);
        if(epoch>1609459200) {
          struct tm local; char stamp[32];
          localtime_r(&epoch,&local); std::strftime(stamp,sizeof(stamp),"%d.%m.%Y %H:%M:%S",&local);
          last_update_->publish_state(stamp);
        } else last_update_->publish_state("Zeit nicht synchronisiert");
      }
      settings_.baseline=raw; save_configuration_(settings_,alignment_,false);build_export_();
      value_->publish_state(raw/std::pow(10.0f,settings_.decimals));
      message_="Zählerstand übernommen";
    }
  }
  // Before the first save there are no previous calibrated ROIs to restore.
  // Retain the tested ROIs rather than sending eight empty boxes to the reader.
  if(test_ && settings_.calibrated) reader_->set_crop_zones(zones(settings_));
  busy_=false;
  next_=millis()+settings_.interval*1000;
}
void MeterSetup::diagnostics_() {
  const bool problem=!settings_.calibrated || reading_problem_ || timed_out_ || stale_;
  const std::string status=stale_&&!busy_?"Keine aktuelle Ablesung":timed_out_?"Zeitüberschreitung":busy_?(test_?"Test läuft":"Ablesung läuft"):capture_pending_?"Kamerabild aufnehmen":light_test_?"Lichttest":!settings_.calibrated?"Nicht eingerichtet":paused_?"Pausiert":reading_problem_?"Ablesung abgewiesen":have_previous_reading_?"OK":"Warte auf erste Ablesung";
  const std::string error=stale_&&reading_error_.empty()?"Warnschwelle ohne gültige Ablesung überschritten":!settings_.calibrated?"Zählerkonfiguration fehlt":reading_error_;
  if(status_sensor_ && status!=diagnostic_status_) {status_sensor_->publish_state(status);diagnostic_status_=status;}
  if(error_sensor_ && error!=diagnostic_error_) {error_sensor_->publish_state(error.empty()?"Kein Fehler":error);diagnostic_error_=error;}
  if(problem_) problem_->publish_state(problem);
}
bool MeterSetup::canHandle(AsyncWebServerRequest *r) const {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  std::string url(r->url_to(url_buf).c_str());
  return url=="/setup" || url.rfind("/meter/",0)==0;
}
std::string MeterSetup::status_() {
  // Only called on the main loop. Avoid floating-point printf in HTTP handlers.
  const auto tenths=static_cast<uint32_t>(std::isfinite(confidence_)?std::max(0.0f,std::min(100.0f,confidence_))*10.0f+0.5f:0);
  std::string out;
  out.reserve(640);
  out="{\"boxes\":"; out+=zones(settings_);
  out+=",\"warning_after\":";out+=std::to_string(runtime_.warning_after);
  out+=",\"reading_age\":";out+=std::isfinite(reading_age_)?std::to_string(uint32_t(reading_age_)):"null";
  out+=",\"stale\":";out+=stale_?"true":"false";
  out+=",\"config_revision\":";out+=std::to_string(config_revision_);
  out+=",\"digit_confidences\":[";
  for(int i=0;i<8;i++){if(i)out+=',';out+=confidence_digits_==digits_&&std::isfinite(digit_confidences_[i])?std::to_string(int(digit_confidences_[i]*10+0.5f)/10.0f):"null";}out+=']';
  out+=",\"decimals\":"; out+=std::to_string(settings_.decimals);
  out+=",\"interval\":"; out+=std::to_string(settings_.interval);
  out+=",\"baseline\":"; out+=std::to_string(settings_.baseline);
  out+=",\"max_step\":"; out+=std::to_string(settings_.max_step);
  out+=",\"calibrated\":"; out+=settings_.calibrated?"true":"false";
  out+=",\"busy\":"; out+=(busy_||capture_pending_)?"true":"false";
  out+=",\"paused\":"; out+=paused_?"true":"false";
  out+=",\"frame\":"; out+=std::to_string(frame_);
  out+=",\"digits\":"; out+=quote(digits_);
  out+=",\"confidence\":"; out+=std::to_string(tenths/10); out+='.'; out+=std::to_string(tenths%10);
  out+=",\"message\":"; out+=quote(message_);
  out+=",\"loop_stack_size\":"; out+=std::to_string(ESPHOME_LOOP_TASK_STACK_SIZE);
  out+=",\"loop_stack_free\":"; out+=std::to_string(uxTaskGetStackHighWaterMark(nullptr));
  out+=",\"http_stack_free\":"; out+=std::to_string(http_stack_free_);
  out+=",\"autofocus_available\":";out+=autofocus_.supported()?"true":"false";
  out+=",\"autofocus_before_reading\":";out+=autofocus_settings_.before_reading?"true":"false";
  out+=",\"autofocus_status\":";out+=quote(autofocus_status_);
  out+=",\"autofocus_error\":";out+=std::to_string(autofocus_.error());
  out+=",\"illumination_available\":";out+=illumination_?"true":"false";
  out+=",\"illumination_led_count\":";out+=std::to_string(illumination_settings_.led_count);
  out+=",\"illumination_led_capacity\":";out+=std::to_string(led_capacity_());
  out+=",\"illumination_enabled\":";out+=illumination_settings_.enabled?"true":"false";
  out+=",\"illumination_brightness\":";out+=std::to_string(illumination_settings_.brightness);
  out+=",\"illumination_settle_ms\":";out+=std::to_string(illumination_settings_.settle_ms);
  out+=",\"illumination_on\":";out+=illumination_on_?"true":"false";
  out+=",\"light_test\":";out+=light_test_?"true":"false";
  out+=",\"alignment_enabled\":";out+=alignment_.enabled?"true":"false";
  out+=",\"reference_ready\":";out+=draft_alignment_.ready?"true":"false";
  out+=",\"reference_revision\":";out+=std::to_string(reference_revision_);
  out+=",\"references\":[";
  for(int k=0;k<2;k++){if(k) out+=',';out+='[';for(int j=0;j<4;j++){if(j) out+=',';out+=std::to_string(draft_alignment_.regions[k][j]);}out+=']';}out+=']';
  out+=",\"preview_available\":";out+=preview_?"true":"false";
  out+=",\"preview_sequence\":";out+=std::to_string(preview_sequence_);
  out+=",\"preview_corrected\":";out+=preview_rgb_?"true":"false";
  out+=",\"alignment_result\":";out+=quote(alignment_result_);
  out+=",\"alignment_ms\":";out+=std::to_string(alignment_ms_);
  out+=",\"reader_phase\":";out+=quote(reader_phase_());
  out+=",\"last_reader_log\":";out+=quote(last_reader_log_);
  out+=",\"reboot_pending\":";out+=reboot_pending_?"true":"false";
  out+=",\"automatic_restarts\":";out+=std::to_string(recovery_.automatic_restarts);
  out+=",\"consecutive_timeouts\":";out+=std::to_string(recovery_.consecutive_timeouts);
  out+=",\"last_fault\":";out+=quote(recovery_.reason);
  out+=",\"fault_timestamp\":";out+=quote(recovery_.timestamp);
  out+=",\"fault_uptime_ms\":";out+=std::to_string(recovery_.uptime_ms);
  out+=",\"fault_phase\":";out+=quote(recovery_.phase);
  out+=",\"fault_reader_log\":";out+=quote(recovery_.reader_log);
  out+=",\"fault_alignment\":";out+=quote(recovery_.alignment);
  out+=",\"fault_frame\":";out+=std::to_string(recovery_.frame);
  out+=",\"fault_free_heap\":";out+=std::to_string(recovery_.free_heap);
  out+=",\"fault_free_psram\":";out+=std::to_string(recovery_.free_psram);
  out+=",\"recovery_delay_ms\":";out+=std::to_string(recovery_delay_ms_);
  out+=",\"reset_count\":"; out+=std::to_string(reset_count_);
  out+=",\"http_task\":"; out+=quote(http_task_name_);
  out+='}'; return out;
}
void MeterSetup::handleRequest(AsyncWebServerRequest *r) {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  std::string url(r->url_to(url_buf).c_str());
  if(url=="/setup" && r->method()==HTTP_GET) { r->send(200,"text/html; charset=utf-8",WEB_UI); return; }
  std::unique_lock<std::mutex> guard(mutex_);
  if(url=="/meter/export" && r->method()==HTTP_GET) {
    auto data=export_json_;guard.unlock();auto *response=r->beginResponse(200,"application/json",data);
    response->addHeader("Content-Disposition","attachment; filename=wasserzaehler-backup.json");response->addHeader("Cache-Control","no-store");r->send(response);return;
  }
  if(url=="/meter/status" && r->method()==HTTP_GET) {
    http_stack_free_=uxTaskGetStackHighWaterMark(nullptr);
    if(http_task_name_.empty()) {
      http_task_name_=pcTaskGetName(nullptr);
      ESP_LOGI("meter_setup", "HTTP task %s, minimum free stack %u bytes", http_task_name_.c_str(), http_stack_free_);
    }
    auto s=status_json_; guard.unlock();
    auto *response=r->beginResponse(200,"application/json",s);
    response->addHeader("Cache-Control","no-store"); r->send(response); return;
  }
  if(url=="/meter/processed" && r->method()==HTTP_GET) {
    if(!preview_) {r->send(503,"text/plain; charset=utf-8","Kein gültiges KI-Bild; Rahmen testen und Ausrichtungsstatus prüfen");return;}
    auto image=preview_;const auto size=preview_size_;const bool rgb=preview_rgb_;
    const auto sequence=preview_sequence_;const auto boxes=preview_boxes_,references=preview_references_;
    guard.unlock();
    auto *response=r->beginResponse(200,rgb?"application/octet-stream":"image/jpeg",image.get(),size);
    response->addHeader("Cache-Control","no-store");response->addHeader("X-Meter-Image",std::to_string(sequence).c_str());
    response->addHeader("X-Meter-Boxes",boxes.c_str());response->addHeader("X-Meter-References",references.c_str());
    r->send(response);return;
  }
  if(url=="/meter/snapshot" && r->method()==HTTP_GET) {
    if(!jpeg_) {r->send(503,"text/plain","Noch kein Bild");return;}
    auto image=jpeg_; auto size=jpeg_size_;
    displayed_jpeg_=image;displayed_size_=size;displayed_frame_=frame_;const auto frame=frame_;guard.unlock();
    auto *response=r->beginResponse(200,"image/jpeg",image.get(),size); response->addHeader("Cache-Control","no-store");response->addHeader("X-Meter-Frame",std::to_string(frame).c_str());r->send(response);return;
  }
  if(r->method()!=HTTP_POST) {r->send(405,"text/plain","POST erforderlich");return;}
  if(!r->hasHeader("X-Meter-Setup")) {r->send(403,"text/plain","Einrichtungsseite verwenden");return;}
  if(url=="/meter/restart") {
    command_=RESTART;r->send(200,"text/plain; charset=utf-8","Neustart vorgemerkt");return;
  }
  if(command_!=NONE || ((busy_ || capture_pending_) && url!="/meter/pause")) {r->send(409,"text/plain","Bitte laufende Aktion abwarten");return;}
  if(url=="/meter/focus" || url=="/meter/focus_save") {
    if(url=="/meter/focus"){
      if(!autofocus_.supported()){r->send(400,"text/plain; charset=utf-8","Autofokus wird von dieser Kamera nicht unterstützt");return;}
      command_=FOCUS;
    } else {
      if(!r->hasParam("enabled")||(r->getParam("enabled")->value()!="0"&&r->getParam("enabled")->value()!="1")){r->send(400,"text/plain","enabled: 0 oder 1 erforderlich");return;}
      pending_autofocus_=r->getParam("enabled")->value()=="1";command_=FOCUS_SAVE;
    }
    r->send(200,"text/plain; charset=utf-8","Fokusaktion vorgemerkt");return;
  }
  if(url=="/meter/import") {
    if(!r->hasParam("data") || r->getParam("data")->value().size()>4096) {r->send(400,"text/plain","Sicherung fehlt oder zu groß");return;}
    pending_import_=r->getParam("data")->value();command_=IMPORT;r->send(200,"text/plain","Import wird geprüft");return;
  }
  if(url=="/meter/light_on" || url=="/meter/light_off" || url=="/meter/light_save") {
    if(!illumination_) {r->send(400,"text/plain; charset=utf-8","LED-Konfiguration mit illumination_id in YAML fehlt");return;}
    IlluminationSettings candidate=illumination_settings_;
    if(url!="/meter/light_off") {
      auto number=[r](const char *name,uint32_t &value)->bool {
        if(!r->hasParam(name))return false;
        const auto &s=r->getParam(name)->value();
        if(s.empty() || s.size()>4 || s.find_first_not_of("0123456789")!=std::string::npos)return false;
        value=std::strtoul(s.c_str(),nullptr,10);return true;
      };
      uint32_t enabled,brightness,settle,count;
      if(!number("enabled",enabled)||enabled>1||!number("brightness",brightness)||brightness<1||brightness>100||!number("settle_ms",settle)||settle>5000||!number("led_count",count)||count<1||count>led_capacity_()) {r->send(400,"text/plain; charset=utf-8","Helligkeit 1–100 Prozent, Vorlauf 0–5000 ms; LED-Anzahl innerhalb der reservierten Kapazität");return;}
      candidate.enabled=enabled;candidate.brightness=brightness;candidate.settle_ms=settle;candidate.led_count=count;
    }
    pending_illumination_=candidate;
    command_=url=="/meter/light_on"?LIGHT_ON:url=="/meter/light_off"?LIGHT_OFF:LIGHT_SAVE;
    r->send(200,"text/plain","Aktion vorgemerkt");return;
  }
  if(url=="/meter/reference" || url=="/meter/test" || url=="/meter/save") {
    pending_warning_after_=runtime_.warning_after;
    if(r->hasParam("warning_after")) {
      const std::string v=r->getParam("warning_after")->value();char *end=nullptr;const auto n=std::strtoul(v.c_str(),&end,10);
      if(v.empty()||*end||n<30||n>86400){r->send(400,"text/plain","Warnschwelle: 30–86400 Sekunden");return;}pending_warning_after_=n;
    }
    pending_alignment_=draft_alignment_;
    if(r->hasParam("alignment")) pending_alignment_.enabled=r->getParam("alignment")->value()=="1";
    if(r->hasParam("references")) {
      const std::string data=r->getParam("references")->value();if(data.size()>96) {r->send(400,"text/plain","Ungültige Referenzbereiche");return;}const char *p=data.c_str();
      for(int i=0;i<8;i++) {
        char *end=nullptr;long v=std::strtol(p,&end,10);
        if(end==p || v<0 || v>640 || (i<7 && *end!=',') || (i==7 && *end!='\0')) {r->send(400,"text/plain","Ungültige Referenzbereiche");return;}
        pending_alignment_.regions[i/4][i%4]=v;p=end+(i<7?1:0);
      }
    }
    if(url=="/meter/reference") {
      if(!valid_reference_regions(pending_alignment_) || !displayed_jpeg_ || !r->hasParam("frame") || r->getParam("frame")->value()!=std::to_string(displayed_frame_)) {r->send(400,"text/plain; charset=utf-8","Neues Bild aufnehmen; zwei Referenzen 16–96 Pixel groß und mindestens 80 Pixel auseinander wählen");return;}
      reference_capture_=displayed_jpeg_;reference_capture_size_=displayed_size_;command_=REFERENCE;
      r->send(200,"text/plain","Referenzen werden vorbereitet");return;
    }
    if(pending_alignment_.enabled && (!draft_alignment_.ready || !valid_reference_regions(pending_alignment_) || std::memcmp(pending_alignment_.regions,draft_alignment_.regions,sizeof(pending_alignment_.regions)))) {r->send(400,"text/plain; charset=utf-8","Referenzbereiche zuerst aus dem angezeigten Bild übernehmen");return;}
  }
  if(url=="/meter/reset") command_=RESET;
  else if(url=="/meter/capture") command_=CAPTURE;
  else if(url=="/meter/pause") command_=PAUSE;
  else if(url=="/meter/resume") command_=RESUME;
  else if(url=="/meter/save" || url=="/meter/test") {
    Settings candidate=settings_; int values[32];
    if(!r->hasParam("boxes") || r->getParam("boxes")->value().size()>256) {r->send(400,"text/plain","32 Koordinaten erforderlich");return;}
    std::string input=r->getParam("boxes")->value(); const char *p=input.c_str();
    for(int i=0;i<32;i++) {
      char *end=nullptr; long v=std::strtol(p,&end,10);
      if(end==p || v<0 || v>640 || (i<31 && *end!=',') || (i==31 && *end!='\0')) {r->send(400,"text/plain","Ungültige Koordinaten");return;}
      values[i]=v; p=end+(i<31?1:0);
    }
    for(int i=0;i<32;i++) candidate.boxes[i/4][i%4]=values[i];
    auto number=[r](const char *name,uint32_t &value)->bool {
      if(!r->hasParam(name)) return false; const auto &s=r->getParam(name)->value();
      if(s.empty() || s.size()>8 || s.find_first_not_of("0123456789")!=std::string::npos) return false;
      value=std::strtoul(s.c_str(),nullptr,10);return true;
    };
    uint32_t decimals;
    if(!number("decimals",decimals) || decimals>6 || !number("interval",candidate.interval) || !number("baseline",candidate.baseline) || !number("max_step",candidate.max_step)) {r->send(400,"text/plain","Ungültige Einstellungen");return;}
    candidate.decimals=decimals;
    if(!valid_(candidate)) {
      const int box=invalid_box_(candidate);
      if(box>=0) {
        char error[160];
        snprintf(error,sizeof(error),"Rahmen %d: Breite/Höhe müssen positiv sein, innerhalb 640×480 liegen und die Mitte rechts vom vorherigen Rahmen stehen.",box+1);
        r->send(400,"text/plain; charset=utf-8",error);
      } else r->send(400,"text/plain; charset=utf-8","Intervall: 10–86400 Sekunden; max. Sprung: 1–99999999; Stand: acht Ziffern.");
      return;
    }
    pending_=candidate; command_=url=="/meter/save"?SAVE:TEST;
  } else {r->send(404,"text/plain","Unbekannt");return;}
  // ESPHome 2026.9.1 maps unsupported HTTP codes (including 202) to 500.
  // The command is queued successfully; return a supported success status.
  r->send(200,"text/plain","Aktion vorgemerkt");
}
void MeterSetup::set_preview_(const std::shared_ptr<uint8_t> &data,size_t size,bool rgb) {
  preview_=data;preview_size_=size;preview_rgb_=rgb;
  preview_boxes_=zones(test_?pending_:settings_);
  preview_references_="[";
  for(int k=0;k<2;k++) {if(k)preview_references_+=',';preview_references_+='[';
    for(int j=0;j<4;j++){if(j)preview_references_+=',';preview_references_+=std::to_string(active_alignment_.regions[k][j]);}preview_references_+=']';
  }
  preview_references_+=']';
}
// Recovery keeps the worker isolated until a reboot; never reuse an unknown live job.
std::string MeterSetup::reader_phase_() const {
  if(capture_pending_&&capture_stage_==3)return "autofocus";
  if(capture_pending_)return capture_stage_==0?"light_warmup":capture_stage_==1?"flush_frame":"snapshot";
  const std::string phase=static_cast<AlignedMeterReader *>(reader_)->phase();
  return inference_started_ && phase=="idle"?"awaiting_result":phase;
}
void MeterSetup::record_fault_(const std::string &reason,bool automatic_restart) {
  const bool changed=reason!=recovery_.reason;
  recovery_.frame=frame_;recovery_.uptime_ms=millis();
  const auto now=std::time(nullptr);
  if(now>1577836800) {auto *local=std::localtime(&now);if(local)std::strftime(recovery_.timestamp,sizeof(recovery_.timestamp),"%d.%m.%Y %H:%M:%S",local);}
  else std::strncpy(recovery_.timestamp,"Zeit nicht synchronisiert",sizeof(recovery_.timestamp)-1);
  recovery_.free_heap=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  recovery_.free_psram=heap_caps_get_free_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  const auto copy=[](char *target,size_t size,const std::string &value){std::strncpy(target,value.c_str(),size-1);target[size-1]=0;};
  copy(recovery_.phase,sizeof(recovery_.phase),reason.rfind("CRITICAL: Camera Frame Failure",0)==0?"camera_frame_timeout":reader_phase_());
  copy(recovery_.reason,sizeof(recovery_.reason),reason);
  copy(recovery_.reader_log,sizeof(recovery_.reader_log),last_reader_log_);
  copy(recovery_.alignment,sizeof(recovery_.alignment),alignment_result_);
  if(automatic_restart){++recovery_.automatic_restarts;++recovery_.consecutive_timeouts;}
  if(automatic_restart || changed || millis()-fault_saved_at_>=900000) {
    if(!recovery_preference_.save(&recovery_) || !global_preferences->sync()) ESP_LOGE("meter_setup","Fehlerdiagnose konnte nicht gespeichert werden");
    save_configuration_(settings_,alignment_,true);fault_saved_at_=millis();
  }
  ESP_LOGW("meter_setup","Ablesefehler: %s; Phase %s; Heap %u; PSRAM %u; Reader %s",recovery_.reason,recovery_.phase,unsigned(recovery_.free_heap),unsigned(recovery_.free_psram),recovery_.reader_log);
}
void MeterSetup::recovery_loop_() {
  if(reboot_pending_ && int32_t(millis()-reboot_at_)>=0) App.safe_reboot();
}

}
