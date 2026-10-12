"""Run production backup/import, health, per-digit parsing and MQTT code on the host."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
header=(root/'components/meter_setup/meter_setup.h').read_text();cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();features=(root/'components/meter_setup/features.cpp').read_text()
structs=header[header.index('struct Settings {'):header.index('class MeterSetup;')]
methods=features[features.index('void MeterSetup::capture_digit_log_('):features.rfind('\n}')]
save_body=cpp[cpp.index('    if(cmd==SAVE) {')+len('    if(cmd==SAVE) {'):cpp.index('    } else {\n      reader_->set_crop_zones')]
validation=cpp[cpp.index('int MeterSetup::invalid_box_('):cpp.index('static std::string zones(const Settings &s) {')]
source=r'''
#include <ArduinoJson.h>
#include <algorithm>
#include <string>
#include <vector>
#include <memory>
#include <mutex>
#include <cmath>
#include <ctime>
#include <cstring>
#include <cstdlib>
#include <cassert>
#include <iostream>
#define USE_MQTT
constexpr int MAC_ADDRESS_BUFFER_SIZE=13;
void get_mac_address_into_buffer(char *b){std::strcpy(b,"112233aabbcc");}
uint32_t tick=0;uint32_t millis(){return tick;}
namespace json {
template<class F>std::string build_json(F f){JsonDocument doc;f(doc.to<JsonObject>());std::string out;serializeJson(doc,out);return out;}
template<class F>bool parse_json(const std::string&s,F f){JsonDocument doc;if(deserializeJson(doc,s))return false;return f(doc.as<JsonObject>());}
}
namespace mqtt {
struct Availability{std::string topic="test/status",payload_available="online",payload_not_available="offline";};
struct Discovery{std::string prefix="homeassistant";bool retain=true;};
struct Publication{std::string topic,payload;bool retain;};
struct Client{bool connected=true,success=true;Discovery discovery;Availability availability;std::vector<Publication> messages;
 bool is_connected(){return connected;}bool is_discovery_enabled(){return true;}Discovery &get_discovery_info(){return discovery;}std::string get_topic_prefix(){return "test";}Availability &get_availability(){return availability;}
 bool publish(const std::string&t,const std::string&p,int,bool r){if(!success)return false;messages.push_back({t,p,r});return true;}
 bool publish(const std::string&t,const char*p,size_t n,int q,bool r){return publish(t,std::string(p,n),q,r);}
}client;Client *global_mqtt_client=&client;
}
struct AppType{std::string get_name(){return "test";}std::string get_friendly_name(){return "Wasserzähler";}}App;
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+structs+r'''
std::string zones(const Settings&){return "saved zones";}
struct Pref {bool fail_next=false;std::vector<uint8_t> data;template<class T>bool save(T*p){if(fail_next){fail_next=false;return false;}auto b=reinterpret_cast<uint8_t*>(p);data.assign(b,b+sizeof(T));return true;}};
struct Globals{bool sync(){return true;}}globals;Globals *global_preferences=&globals;
struct Sensor{float state=NAN;void publish_state(float v){state=v;}};
struct Binary{bool state=false;void publish_state(bool v){state=v;}};
struct Reader{std::string zones;void set_crop_zones(const std::string&s){zones=s;}};
class MeterSetup {
public:
 Settings settings_{},pending_{};AlignmentReference alignment_{},draft_alignment_{},pending_alignment_{};IlluminationSettings illumination_settings_{},pending_illumination_{};RuntimeSettings runtime_{};
 std::mutex mutex_;bool busy_=true,timed_out_=false,test_=false,stale_=false,paused_=false,accepted_=false,reading_problem_=false,have_previous_reading_=false,light_test_=false,mqtt_discovered_=false;
 std::string export_json_,pending_import_,message_,reading_error_,confidence_digits_,digits_;float digit_confidences_[8]{},reading_age_=NAN,confidence_=0;
 uint32_t pending_warning_after_=0,next_=0,health_updated_=0,last_accepted_at_=0,boot_started_=0,config_revision_=0,mqtt_image_sequence_=0,preview_sequence_=1;
 std::shared_ptr<uint8_t> preview_,inference_jpeg_;size_t preview_size_=0,inference_jpeg_size_=0;
 Sensor changes,flows;Sensor *change_=&changes,*flow_=&flows;
 Sensor age;Sensor *age_sensor_=&age;Binary stale;Binary *stale_sensor_=&stale;Reader reader;Reader *reader_=&reader;
 Pref illumination_preference_,runtime_preference_;Configuration saved{};
 uint16_t led_capacity_()const{return 64;}bool save_configuration_(const Settings &s,const AlignmentReference&a,bool){saved.settings=s;saved.alignment=a;return true;}
 void set_illumination_(bool,const IlluminationSettings&){}
 void apply_save_(){
'''+save_body+r'''
 }
 static int invalid_box_(const Settings&);static bool valid_(const Settings&);
 void capture_digit_log_(const char*,const char*,size_t);void features_loop_();void build_export_();void import_config_();void mqtt_loop_();
};
'''+validation+methods+r'''
int main(){
 MeterSetup original;original.settings_.calibrated=1;original.settings_.baseline=1864266;original.runtime_.warning_after=600;original.illumination_settings_.led_count=6;
 for(int i=0;i<8;i++){auto &b=original.settings_.boxes[i];b[0]=20+i*50;b[1]=100;b[2]=b[0]+30;b[3]=150;}
 original.alignment_.enabled=original.alignment_.ready=1;uint16_t regions[2][4]={{100,200,132,232},{450,200,482,232}};memcpy(original.alignment_.regions,regions,sizeof(regions));for(auto &row:original.alignment_.pixels)for(int i=0;i<256;i++)row[i]=i%2?20:200;
 original.build_export_();assert(original.export_json_.size()<3000);assert(original.export_json_.find("password")==std::string::npos);
 MeterSetup restored;restored.pending_import_=original.export_json_;restored.import_config_();assert(restored.settings_.baseline==1864266&&restored.runtime_.warning_after==600&&restored.illumination_settings_.led_count==6&&restored.paused_&&restored.config_revision_==1);
 assert(memcmp(restored.alignment_.pixels,original.alignment_.pixels,sizeof(original.alignment_.pixels))==0&&restored.reader.zones.find("[20,100,50,150]")!=std::string::npos);
 auto corrupt=[&](const char *field,auto value){JsonDocument d;deserializeJson(d,original.export_json_);d[field]=value;std::string data;serializeJson(d,data);restored.pending_import_=data;restored.import_config_();assert(restored.config_revision_==1&&restored.settings_.baseline==1864266&&restored.message_.find("abgelehnt")!=std::string::npos);};
 corrupt("version",2);corrupt("camera_width",320);corrupt("warning_after",0);
 restored.illumination_preference_.fail_next=true;restored.pending_import_=original.export_json_;restored.import_config_();assert(restored.config_revision_==1&&restored.saved.settings.baseline==1864266&&restored.message_.find("fehlgeschlagen")!=std::string::npos);
 restored.pending_=restored.settings_;restored.pending_alignment_=restored.alignment_;restored.pending_warning_after_=900;restored.runtime_preference_.fail_next=true;restored.apply_save_();assert(restored.runtime_.warning_after==600&&restored.message_.find("Warnschwelle")!=std::string::npos);restored.apply_save_();assert(restored.runtime_.warning_after==900&&restored.message_=="Gespeichert");
 const std::string log="[I] Result: VALID (Raw: 01864266, Conf: 0.980, [0.992, 0.992, 0.992, 0.973, 0.934, 0.992, 0.996, 0.969])";
 restored.capture_digit_log_("meter_reader_tflite",log.data(),log.size());assert(restored.confidence_digits_=="01864266"&&std::abs(restored.digit_confidences_[4]-93.4f)<.01f);
 restored.confidence_digits_.clear();const std::string malformed="Result: VALID (Raw: 01864266, Conf: 0.980, [0.992])";restored.capture_digit_log_("meter_reader_tflite",malformed.data(),malformed.size());assert(restored.confidence_digits_.empty());
 restored.runtime_.warning_after=30;restored.have_previous_reading_=true;restored.last_accepted_at_=5000;tick=35000;restored.features_loop_();assert(restored.stale_&&restored.stale.state&&restored.age.state==30);
 restored.last_accepted_at_=tick;tick+=5000;restored.features_loop_();assert(!restored.stale_&&restored.age.state==5);
 mqtt::client.messages.clear();restored.mqtt_discovered_=false;restored.busy_=false;restored.test_=false;restored.inference_jpeg_=std::shared_ptr<uint8_t>(new uint8_t[4]{255,216,0,217},std::default_delete<uint8_t[]>());restored.inference_jpeg_size_=4;restored.mqtt_loop_();assert(mqtt::client.messages.size()==2);
 JsonDocument discovery;deserializeJson(discovery,mqtt::client.messages[0].payload);assert(discovery["device"]["identifiers"]=="112233aabbcc"&&discovery["topic"]=="test/camera/image"&&discovery["availability_topic"]=="test/status");assert(mqtt::client.messages[1].payload.size()==4&&mqtt::client.messages[1].payload[2]==0&&mqtt::client.messages[1].retain);
 restored.mqtt_loop_();assert(mqtt::client.messages.size()==2);restored.test_=true;++restored.preview_sequence_;restored.mqtt_loop_();assert(mqtt::client.messages.size()==2);restored.test_=false;mqtt::client.success=false;restored.mqtt_loop_();assert(restored.mqtt_image_sequence_==1);mqtt::client.success=true;restored.mqtt_loop_();assert(mqtt::client.messages.size()==3);
 std::cout<<"Features passed: backup/reference roundtrip, strict validation/rollback, per-digit matching, age warning/recovery, camera discovery/MAC, binary JPEG/retain/retry/test isolation\n";
}
'''
include=root/'.esphome/build/wasserzaehler/managed_components/bblanchon__arduinojson/src'
with tempfile.TemporaryDirectory(prefix='meter-features-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-I',str(include),'-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
