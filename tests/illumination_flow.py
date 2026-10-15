"""Production illumination sequencing with fake clock, camera, LED output and preferences."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
header=(root/'components/meter_setup/meter_setup.h').read_text()
settings=header[header.index('struct Settings {'):header.index('class MeterSetup')]
fields=header[header.index('  light::AddressableLightState *illumination_'):header.index('  ESPPreferenceObject preference_;')]
methods=cpp[cpp.index('uint16_t MeterSetup::led_capacity_() const'):cpp.index('void MeterSetup::start_(bool test)')]
image=cpp[cpp.index('void MeterSetup::on_camera_image('):cpp.index('void MeterSetup::reset_()')]
load=cpp[cpp.index('  illumination_preference_=global_preferences->make_preference<IlluminationSettings>'):cpp.index('  camera_->add_listener(this);')]
source=r'''
#include <cassert>
#include <memory>
#include <mutex>
#include <string>
#include <map>
#include <vector>
#include <iostream>
#include <cstdlib>
#define MALLOC_CAP_SPIRAM 0
#define MALLOC_CAP_8BIT 0
void *heap_caps_malloc(size_t n,int){return malloc(n);}
void heap_caps_free(void *p){free(p);}
uint32_t now=100;uint32_t millis(){return now;}
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+settings+r'''
std::map<uint32_t,std::vector<uint8_t>> storage;
struct ESPPreferenceObject {
 uint32_t key=0;
 template<class T>bool save(const T *s){auto p=reinterpret_cast<const uint8_t*>(s);storage[key]=std::vector<uint8_t>(p,p+sizeof(T));return true;}
 template<class T>bool load(T *s){auto i=storage.find(key);if(i==storage.end()||i->second.size()!=sizeof(T))return false;memcpy(s,i->second.data(),sizeof(T));return true;}
};
struct Globals {bool success=true;bool sync(){return success;}template<class T>ESPPreferenceObject make_preference(uint32_t k){return {k};}} globals;
Globals *global_preferences=&globals;
namespace light {
enum class ColorMode {RGB_WHITE};
struct LightState;
struct Call {LightState *light;bool on=false,has_transition=false,has_effect=false;float brightness=0,r=0,g=0,b=0,w=0;
 Call &set_transition_length(int value){assert(value==0);has_transition=true;return *this;}Call &set_save(bool value){assert(!value);return *this;}
 Call &set_effect(const char *name){assert(std::string(name)=="Zählerlicht");has_effect=true;return *this;}Call &set_state(bool v){on=v;return *this;}Call &set_color_mode(ColorMode){return *this;}Call &set_rgbw(float a,float bb,float c,float d){r=a;g=bb;b=c;w=d;return *this;}Call &set_brightness(float v){brightness=v;return *this;}void perform();};
struct AddressableLight {int capacity=64;int size()const{return capacity;}};
struct LightState {AddressableLight output;AddressableLight *get_output()const{return const_cast<AddressableLight*>(&output);}bool on=false;float brightness=0;Call make_call(){return {this};}};
void Call::perform(){assert(!(has_effect&&has_transition));assert(on||!has_effect);light->on=on;if(on){assert(r==0&&g==0&&b==0&&w==1);light->brightness=brightness;}}
using AddressableLightState=LightState;
}
struct CountedWhiteEffect {explicit CountedWhiteEffect(void*){}};
namespace camera {enum CameraRequester{WEB_REQUESTER};struct CameraImage{std::vector<uint8_t> data=std::vector<uint8_t>(20,3);size_t get_data_length(){return data.size();}uint8_t *get_data_buffer(){return data.data();}};}
struct Camera {int requests=0,streams=0,stops=0;void stop_stream(camera::CameraRequester){++stops;}void start_stream(camera::CameraRequester){++streams;}void request_image(camera::CameraRequester){++requests;}};
struct Reader {bool paused=true;int updates=0;virtual ~Reader(){};void set_pause_processing(bool v){paused=v;}void update(){++updates;}};
struct AlignedMeterReader:Reader {int arms=0;void arm_for_capture(){++arms;}};
class MeterSetup {
 public:
'''+fields+r'''
 Camera camera;Camera *camera_=&camera;AlignedMeterReader reader;Reader *reader_=&reader;
 struct Power{bool available=false,awake=true;int requests=0;void request(){++requests;}bool supported(){return available;}bool ready(){return awake;}uint32_t generation(){return 0;}}camera_power_;
 bool manual_focus_once_=false;
 uint32_t autofocus_power_generation_=UINT32_MAX;
 AutofocusSettings autofocus_settings_{1,0};bool autofocus_once_=false,autofocus_used_=false;struct AF{bool supported(){return false;}}autofocus_;bool start_autofocus_(){return false;}void autofocus_loop_(){}
 bool live_=false,live_streaming_=false;uint32_t live_last_frame_=0,live_frame_at_=0;
 Settings settings_;std::mutex mutex_;bool busy_=false,test_=false,reading_problem_=false;std::string message_,reading_error_;
 uint32_t next_=0,frame_=0;std::shared_ptr<uint8_t> jpeg_;size_t jpeg_size_=0;
 void load_(){
'''+load+r'''
 }
 uint16_t led_capacity_()const;bool accepts_reader_frame_();void set_illumination_(bool,const IlluminationSettings&);bool save_illumination_(const IlluminationSettings&);void reset_illumination_();void begin_capture_(bool);void illumination_loop_();void on_camera_image(const std::shared_ptr<camera::CameraImage>&);
};
'''+methods+image+r'''
int main(){
 // The previous 8-byte LED settings migrate without altering brightness/timing.
 LegacyIlluminationSettings previous;previous.enabled=1;previous.brightness=55;previous.settle_ms=1200;
 globals.make_preference<LegacyIlluminationSettings>(0x7a32b904).save(&previous);
 MeterSetup migration;migration.load_();assert(migration.illumination_settings_.version==2&&migration.illumination_settings_.enabled&&migration.illumination_settings_.brightness==55&&migration.illumination_settings_.settle_ms==1200&&migration.illumination_settings_.led_count==8);
 storage.clear();
 light::LightState lamp;auto img=std::make_shared<camera::CameraImage>();
 MeterSetup owner;owner.illumination_=&lamp;owner.load_();assert(!lamp.on&&!owner.illumination_settings_.enabled);
 owner.busy_=true;owner.begin_capture_(true);assert(owner.reader.updates==1&&owner.reader.arms==1&&owner.camera.requests==1&&owner.accepts_reader_frame_()); // Disabled path has no extra delay.
 IlluminationSettings options;options.enabled=1;options.brightness=45;options.settle_ms=1000;options.led_count=6;
 assert(owner.save_illumination_(options));owner.pending_illumination_=options;
 MeterSetup reboot;reboot.illumination_=&lamp;reboot.load_();assert(reboot.illumination_settings_.led_count==6&&reboot.illumination_settings_.brightness==45&&!lamp.on);
 MeterSetup photo;photo.illumination_=&lamp;photo.load_();photo.begin_capture_(false);assert(lamp.on&&lamp.brightness==.45f&&photo.camera.requests==0);
 photo.on_camera_image(img);assert(photo.frame_==0);now=1099;photo.illumination_loop_();assert(photo.camera.requests==0);
 now=1100;photo.illumination_loop_();assert(photo.camera.requests==1&&photo.capture_stage_==1);photo.on_camera_image(img);assert(photo.frame_==0&&photo.flush_received_);
 photo.illumination_loop_();assert(photo.camera.requests==2&&photo.capture_pending_);photo.on_camera_image(img);assert(photo.frame_==1&&!photo.capture_pending_&&!lamp.on);
 MeterSetup live;live.illumination_=&lamp;live.load_();live.live_=true;live.begin_capture_(false);now+=1000;live.illumination_loop_();live.on_camera_image(img);live.illumination_loop_();live.on_camera_image(img);assert(live.live_streaming_&&live.camera.streams==1&&lamp.on&&!live.capture_pending_);live.on_camera_image(img);assert(live.camera.streams==1&&live.frame_==2);
 MeterSetup reading;reading.illumination_=&lamp;reading.load_();reading.busy_=true;reading.begin_capture_(true);assert(!reading.accepts_reader_frame_());
 now+=1000;reading.illumination_loop_();reading.on_camera_image(img);reading.illumination_loop_();assert(reading.reader.updates==1&&reading.reader.arms==1&&reading.accepts_reader_frame_()&&lamp.on);
 MeterSetup timeout;timeout.illumination_=&lamp;timeout.load_();timeout.busy_=true;timeout.begin_capture_(true);now+=15001;timeout.illumination_loop_();assert(!lamp.on&&!timeout.busy_&&!timeout.capture_pending_&&timeout.reading_problem_&&timeout.reader.updates==0);
 owner.light_test_=true;owner.pending_illumination_.brightness=70;owner.light_test_deadline_=now+120000;owner.begin_capture_(false);assert(lamp.on&&lamp.brightness==.7f);now+=1000;owner.illumination_loop_();owner.on_camera_image(img);owner.illumination_loop_();owner.on_camera_image(img);assert(lamp.on);owner.busy_=false;now+=120000;owner.illumination_loop_();assert(!owner.light_test_&&!lamp.on);
 globals.success=false;options.brightness=80;assert(!reboot.save_illumination_(options));assert(reboot.illumination_settings_.brightness==45);IlluminationSettings rolled;reboot.illumination_preference_.load(&rolled);assert(rolled.brightness==45);globals.success=true;
 lamp.output.capacity=2;reboot.reset_illumination_();assert(reboot.illumination_settings_.led_count==2);MeterSetup cleared;cleared.load_();assert(!cleared.illumination_settings_.enabled&&!lamp.on);
 std::cout<<"Illumination flow passed: persistence/rollback/reset, disabled path, white channel, warmup, stale-frame discard, inference handoff, timeout shutoff, manual preview and 2-minute limit\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-light-flow-') as temp:
 binary=str(Path(temp)/'test')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
