"""Production image controls in the actual wake/light/focus/frame preparation pipeline."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
fixture=root/'tests/illumination_flow.py';scope={'__file__':str(fixture)}
exec(fixture.read_text().split('with tempfile.TemporaryDirectory(')[0],scope)
source=scope['source'];source=source[:source.index('int main()')]
source=source.replace('uint32_t generation(){return 0;}', 'uint32_t gen=0;uint32_t generation(){return gen;}')
source=source.replace(' ImageSettings image_settings_{},pending_image_{},active_image_{};bool image_controls_available_(){return false;}bool prepare_image_settings_(){return true;}', ''' ImageLimits image_limits_{};ImageSettings image_settings_{},pending_image_{},active_image_{},applied_image_{};ESPPreferenceObject image_preference_;bool image_applied_=false;uint32_t image_power_generation_=UINT32_MAX,image_settle_until_=0;std::string image_status_;bool image_controls_available_()const;bool prepare_image_settings_();void image_setup_();''')
source=source.replace('class MeterSetup {',r'''
#define ESP_LOGW(...) ((void)0)
bool fail_write=false,sensor_available=true;int writes=0;int values[5]={};
constexpr int OV5640_PID=0x5640,OV3660_PID=0x3660;
struct sensor_t {struct{int PID;}id;int (*set_exposure_ctrl)(sensor_t*,int);int (*set_ae_level)(sensor_t*,int);int (*set_contrast)(sensor_t*,int);int (*set_saturation)(sensor_t*,int);int (*set_wb_mode)(sensor_t*,int);};
int set(int index,int value){writes++;if(fail_write)return -1;values[index]=value;return 0;}
sensor_t sensor{{OV5640_PID},[](sensor_t*,int v){return set(0,v);},[](sensor_t*,int v){return set(1,v);},[](sensor_t*,int v){return set(2,v);},[](sensor_t*,int v){return set(3,v);},[](sensor_t*,int v){return set(4,v);}};
sensor_t *esp_camera_sensor_get(){return sensor_available?&sensor:nullptr;}
class MeterSetup {''')
cpp=(root/'components/meter_setup/image_controls.cpp').read_text();source+=cpp[cpp.index('bool MeterSetup::image_controls_available_()'):cpp.rfind('\n}')]
source+=r'''
int main(){
 MeterSetup owner;owner.image_setup_();assert(owner.image_settings_==ImageSettings{});
 owner.pending_image_.exposure=-1;owner.pending_image_.contrast=1;owner.pending_image_.saturation=-1;owner.pending_image_.white_balance=3;owner.preview_active_=true;
 owner.begin_capture_(false);owner.illumination_loop_();assert(writes==5&&owner.camera.requests==0&&owner.capture_pending_&&values[0]==1&&values[1]==-1&&values[2]==1&&values[3]==-1&&values[4]==3);now+=299;owner.illumination_loop_();assert(owner.camera.requests==0);now++;owner.illumination_loop_();assert(owner.camera.requests==1);
 auto frame=std::make_shared<camera::CameraImage>();owner.on_camera_image(frame);owner.illumination_loop_();owner.on_camera_image(frame);assert(!owner.capture_pending_&&owner.frame_==1&&!owner.preview_active_&&owner.image_settings_==ImageSettings{});
 owner.begin_capture_(true);owner.illumination_loop_();assert(values[1]==0&&values[2]==0&&writes==10);now+=300;owner.illumination_loop_();assert(owner.reader.updates==0);owner.on_camera_image(frame);owner.illumination_loop_();assert(owner.reader.updates==1&&owner.inference_started_);owner.on_camera_image(frame);
 owner.begin_capture_(false);owner.illumination_loop_();assert(writes==10); // Identical settings do not cause repeated settling.
 owner.capture_pending_=false;owner.camera_power_.gen++;owner.begin_capture_(false);owner.illumination_loop_();assert(writes==15); // Reapply after sensor wake.
 owner.capture_pending_=false;owner.focus_only_=true;owner.pending_image_.exposure=2;owner.preview_active_=true;owner.begin_capture_(false);owner.illumination_loop_();assert(writes==15); // Lens-only controls leave image registers alone.
 ImageSettings saved;saved.exposure=-5;saved.contrast=3;saved.saturation=-4;saved.white_balance=4;owner.image_preference_.save(&saved);MeterSetup reboot;reboot.image_setup_();assert(reboot.image_settings_==saved&&reboot.pending_image_==saved);
 sensor.id.PID=0x2640;MeterSetup other;other.image_setup_();assert(other.image_settings_.exposure==-2&&other.image_settings_.contrast==2&&other.image_settings_.saturation==-2);sensor.id.PID=OV5640_PID;
 saved.exposure=100;owner.image_preference_.save(&saved);MeterSetup bad;bad.image_setup_();assert(bad.image_settings_==ImageSettings{});
 fail_write=true;MeterSetup failed;failed.busy_=true;failed.begin_capture_(true);failed.illumination_loop_();assert(!failed.capture_pending_&&!failed.busy_&&failed.reading_problem_&&failed.reader.updates==0&&failed.next_==now+60000&&failed.camera.requests==0);fail_write=false;
 sensor_available=false;MeterSetup unavailable;assert(!unavailable.image_controls_available_());unavailable.begin_capture_(true);assert(unavailable.inference_started_&&unavailable.reader.updates==1);
 std::cout<<"Image pipeline passed: draft preview, saved parameters restored for OCR, 300ms settle, stale-frame discard, wake reapply, focus-only isolation, restart, invalid preferences and sensor failures\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-image-controls-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
