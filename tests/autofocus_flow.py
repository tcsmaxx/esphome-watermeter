"""Combine production illumination and AF sequencing with hardware fakes."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
# Reuse the existing host harness without running its compiler or main tests.
fixture=root/'tests/illumination_flow.py';scope={'__file__':str(fixture)}
exec(fixture.read_text().split('with tempfile.TemporaryDirectory(')[0],scope)
source=scope['source'];source=source[:source.index('int main()')]
source=source.replace(' AutofocusSettings autofocus_settings_{1,0};bool autofocus_once_=false,autofocus_used_=false;struct AF{bool supported(){return false;}}autofocus_;bool start_autofocus_(){return false;}void autofocus_loop_(){}', ''' AutofocusSettings autofocus_settings_{};bool autofocus_once_=false,autofocus_used_=false;AutofocusController autofocus_;
 ESPPreferenceObject autofocus_preference_;std::string autofocus_status_;bool reboot_pending_=false,paused_=false;uint32_t reboot_at_=0;int faults=0;
 void autofocus_setup_();bool start_autofocus_();void autofocus_loop_();void autofocus_failed_(const char*);void record_fault_(const std::string&,bool automatic){assert(automatic);++faults;}''')
source=source.replace('class MeterSetup {', '''struct AutofocusController {enum State{IDLE,RUNNING,FOCUSED,FAILED,HUNG};State value=IDLE;bool available=true,start_ok=true;int starts=0;void invalidate(){}bool supported(){return available;}bool start(){++starts;value=RUNNING;return start_ok;}State state(){return value;}};
class MeterSetup {''')
cpp=(root/'components/meter_setup/autofocus_flow.cpp').read_text();source+=cpp[cpp.index('void MeterSetup::autofocus_setup_()'):cpp.rfind('\n}')]
source+=r'''
int main(){
 MeterSetup sleepy;sleepy.camera_power_.available=true;sleepy.camera_power_.awake=false;sleepy.begin_capture_(true);sleepy.illumination_loop_();assert(sleepy.capture_stage_==0&&sleepy.reader.paused&&sleepy.autofocus_.starts==0&&sleepy.camera_power_.requests==1);sleepy.camera_power_.awake=true;sleepy.illumination_loop_();assert(sleepy.capture_stage_==3&&sleepy.autofocus_.starts==1);
 MeterSetup af;af.settings_.interval=60;af.busy_=true;af.illumination_settings_.enabled=1;af.illumination_settings_.settle_ms=200;light::LightState lamp;af.illumination_=&lamp;
 af.begin_capture_(true);assert(af.capture_stage_==0&&lamp.on&&af.reader.paused);now+=199;af.illumination_loop_();assert(af.autofocus_.starts==0);now+=1;af.illumination_loop_();assert(af.autofocus_.starts==1&&af.capture_stage_==3&&af.capture_pending_&&af.reader.paused);
 auto frame=std::make_shared<camera::CameraImage>();af.on_camera_image(frame);assert(af.frame_==0);af.illumination_loop_();assert(af.capture_stage_==3&&af.camera.requests==0);
 af.autofocus_.value=AutofocusController::FOCUSED;af.illumination_loop_();assert(af.capture_stage_==1&&af.camera.requests==1&&af.reader.paused);af.on_camera_image(frame);af.illumination_loop_();assert(af.capture_stage_==2&&!af.capture_pending_&&af.inference_started_&&!af.reader.paused&&af.camera.requests==2);
 MeterSetup manual;manual.autofocus_once_=true;manual.begin_capture_(false);manual.illumination_loop_();assert(manual.capture_stage_==3);manual.autofocus_.value=AutofocusController::FOCUSED;manual.illumination_loop_();manual.on_camera_image(frame);manual.illumination_loop_();manual.on_camera_image(frame);assert(!manual.capture_pending_&&manual.reader.paused&&manual.autofocus_status_=="Fokus gefunden"&&manual.frame_==1);
 MeterSetup fail;fail.busy_=true;fail.begin_capture_(true);fail.illumination_loop_();fail.autofocus_.value=AutofocusController::FAILED;fail.illumination_loop_();assert(!fail.busy_&&!fail.capture_pending_&&fail.reading_problem_&&fail.reader.paused&&!fail.reboot_pending_&&fail.next_==now+60000);
 MeterSetup hung;hung.busy_=true;hung.begin_capture_(true);hung.illumination_loop_();hung.autofocus_.value=AutofocusController::HUNG;hung.illumination_loop_();assert(hung.reboot_pending_&&hung.busy_&&hung.paused_&&hung.reader.paused&&hung.faults==1&&hung.reboot_at_==now+5000);
 MeterSetup old;old.autofocus_.available=false;old.begin_capture_(true);assert(old.inference_started_&&!old.capture_pending_&&old.autofocus_.starts==0);
 MeterSetup disabled;disabled.autofocus_settings_.before_reading=0;disabled.begin_capture_(true);assert(disabled.inference_started_&&disabled.autofocus_.starts==0);
 MeterSetup reloaded;AutofocusSettings saved;saved.before_reading=0;auto p=global_preferences->make_preference<AutofocusSettings>(0x7a32b909);p.save(&saved);reloaded.autofocus_setup_();assert(!reloaded.autofocus_settings_.before_reading);
 std::cout<<"AF flow passed: lighting before focus, no OCR during focus, discard stale frame, manual preview, persistent option, focus rejection/retry, hung-worker recovery and OV3660 compatibility\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-af-flow-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
