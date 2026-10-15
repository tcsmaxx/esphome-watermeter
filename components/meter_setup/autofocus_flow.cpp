#include "meter_setup.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
void MeterSetup::autofocus_setup_() {
  autofocus_preference_=global_preferences->make_preference<AutofocusSettings>(0x7a32b909);
  AutofocusSettings saved;if(autofocus_preference_.load(&saved)&&saved.version==1&&saved.before_reading<=1)autofocus_settings_=saved;
  autofocus_status_=autofocus_.supported()?"Bereit · noch nicht fokussiert":"Kamera ohne Autofokus";
}
bool MeterSetup::start_autofocus_() {
  if(!autofocus_once_&&(!autofocus_settings_.before_reading||!autofocus_.supported()))return false;
  autofocus_once_=false;autofocus_used_=true;
  if(autofocus_power_generation_!=camera_power_.generation()){autofocus_.invalidate();autofocus_power_generation_=camera_power_.generation();}
  if(!autofocus_.start()){autofocus_failed_("Autofokus konnte nicht gestartet werden");return true;}
  capture_stage_=3;autofocus_status_="Fokussierung läuft";message_="Fokussierung läuft …";return true;
}
void MeterSetup::autofocus_failed_(const char *reason) {
  autofocus_status_=reason;message_=reason;capture_pending_=false;inference_started_=false;busy_=false;
  reader_->set_pause_processing(true);set_illumination_(light_test_,pending_illumination_);
  if(capture_inference_&&!test_){reading_problem_=true;reading_error_=reason;}
  next_=millis()+settings_.interval*1000;
}
void MeterSetup::autofocus_loop_() {
  if(!capture_pending_||capture_stage_!=3)return;
  const auto state=autofocus_.state();
  if(state==AutofocusController::RUNNING)return;
  if(state==AutofocusController::HUNG){
    autofocus_status_="Autofokus-Zeitlimit überschritten";reading_problem_=true;reading_error_=autofocus_status_;message_=autofocus_status_+"; automatischer Neustart";
    record_fault_(autofocus_status_,true);paused_=true;busy_=true;reboot_pending_=true;reboot_at_=millis()+5000;
    set_illumination_(false,illumination_settings_);reader_->set_pause_processing(true);return;
  }
  if(state!=AutofocusController::FOCUSED){autofocus_failed_("Fokus nicht gefunden; Beleuchtung/Abstand prüfen");return;}
  autofocus_status_="Fokus gefunden";message_="Fokus gefunden; neues Bild wird aufgenommen";
  capture_stage_=1;flush_received_=false;camera_->request_image(camera::WEB_REQUESTER);
}
}
