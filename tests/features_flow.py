"""Run production backup/import, health, per-digit parsing and MQTT code on the host."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
header=(root/'components/meter_setup/meter_setup.h').read_text();cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();features=(root/'components/meter_setup/features.cpp').read_text()
structs=header[header.index('struct Settings {'):header.index('class MeterSetup;')]
methods=features[features.index('void MeterSetup::capture_digit_log_('):features.rfind('\n}')]
a=methods.index('void AlignedMeterReader::loop()');b=methods.index('void MeterSetup::features_loop_()',a);methods=methods[:a]+methods[b:]
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
#define ESP_LOGW(...) ((void)0)
constexpr int MAC_ADDRESS_BUFFER_SIZE=13;
void get_mac_address_into_buffer(char *b){std::strcpy(b,"112233aabbcc");}
uint32_t tick=0;uint32_t millis(){return tick;}
struct TimestampJpeg{std::shared_ptr<uint8_t> data;size_t size=0;};
int annotation_count=0;std::time_t annotated_capture=0;TimestampJpeg timestamp_jpeg(const uint8_t*,size_t,std::time_t captured){++annotation_count;annotated_capture=captured;return {};}
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
struct Sensor{float state=NAN;bool has_state(){return !std::isnan(state);}void publish_state(float v){state=v;}};
namespace sensor {using Sensor=::Sensor;}
struct Text{std::string state;};
struct Binary{bool state=false;void publish_state(bool v){state=v;}};
struct Reader{std::string zones;void set_crop_zones(const std::string&s){zones=s;}};
class MeterSetup {
public:
 Settings settings_{},pending_{};AlignmentReference alignment_{},draft_alignment_{},pending_alignment_{};IlluminationSettings illumination_settings_{},pending_illumination_{};RuntimeSettings runtime_{};
 std::mutex mutex_;bool busy_=true,timed_out_=false,test_=false,stale_=false,paused_=false,accepted_=false,reading_problem_=false,have_previous_reading_=false,light_test_=false,mqtt_discovered_=false;
 std::string export_json_,pending_import_,message_,reading_error_,confidence_digits_,digits_;float digit_confidences_[8]{},reading_age_=NAN,confidence_=0;
 uint32_t pending_warning_after_=0,next_=0,health_updated_=0,last_accepted_at_=0,boot_started_=0,config_revision_=0,mqtt_image_sequence_=0,preview_sequence_=1;
 std::shared_ptr<uint8_t> preview_,inference_jpeg_;size_t preview_size_=0,inference_jpeg_size_=0;std::time_t inference_capture_epoch_=0;uint32_t timestamped_sequence_=0;
 Sensor changes,flows,value,confidence;Sensor *change_=&changes,*flow_=&flows,*value_=&value,*confidence_sensor_=&confidence,*digit_sensors_[8]{};Text *last_update_=nullptr,*status_sensor_=nullptr,*error_sensor_=nullptr;
 bool confidence_pending_=false;uint32_t confidence_finished_at_=0,mqtt_state_at_=0;uint8_t mqtt_discovery_index_=0;
 Sensor age;Sensor *age_sensor_=&age;Binary stale;Binary *stale_sensor_=&stale;Reader reader;Reader *reader_=&reader;
 AutofocusSettings autofocus_settings_{};Pref autofocus_preference_;
 Pref illumination_preference_,runtime_preference_;Configuration saved{};
 uint16_t led_capacity_()const{return 64;}bool save_configuration_(const Settings &s,const AlignmentReference&a,bool){saved.settings=s;saved.alignment=a;return true;}
 void set_illumination_(bool,const IlluminationSettings&){}
 void apply_save_(){
'''+save_body+r'''
 }
 static int invalid_box_(const Settings&);static bool valid_(const Settings&);
 void capture_digit_scores_(const std::string&,const float*);
 void capture_digit_log_(const char*,const char*,size_t);void features_loop_();void build_export_();void import_config_();void mqtt_loop_();
};
'''+validation+methods+r'''
int main(){
 MeterSetup original;original.settings_.calibrated=1;original.settings_.baseline=1864266;original.runtime_.warning_after=600;original.autofocus_settings_.before_reading=0;original.illumination_settings_.led_count=6;
 for(int i=0;i<8;i++){auto &b=original.settings_.boxes[i];b[0]=20+i*50;b[1]=100;b[2]=b[0]+30;b[3]=150;}
 original.alignment_.enabled=original.alignment_.ready=1;uint16_t regions[2][4]={{100,200,132,232},{450,200,482,232}};memcpy(original.alignment_.regions,regions,sizeof(regions));for(auto &row:original.alignment_.pixels)for(int i=0;i<256;i++)row[i]=i%2?20:200;
 original.build_export_();assert(original.export_json_.size()<3000);assert(original.export_json_.find("password")==std::string::npos);
 MeterSetup restored;restored.pending_import_=original.export_json_;restored.import_config_();assert(restored.settings_.baseline==1864266&&restored.runtime_.warning_after==600&&restored.illumination_settings_.led_count==6&&restored.paused_&&restored.config_revision_==1&&!restored.autofocus_settings_.before_reading);
 assert(memcmp(restored.alignment_.pixels,original.alignment_.pixels,sizeof(original.alignment_.pixels))==0&&restored.reader.zones.find("[20,100,50,150]")!=std::string::npos);
 auto corrupt=[&](const char *field,auto value){JsonDocument d;deserializeJson(d,original.export_json_);d[field]=value;std::string data;serializeJson(d,data);restored.pending_import_=data;restored.import_config_();assert(restored.config_revision_==1&&restored.settings_.baseline==1864266&&restored.message_.find("abgelehnt")!=std::string::npos);};
 corrupt("autofocus_before_reading",1);corrupt("version",2);corrupt("camera_width",320);corrupt("warning_after",0);
 restored.illumination_preference_.fail_next=true;restored.pending_import_=original.export_json_;restored.import_config_();assert(restored.config_revision_==1&&restored.saved.settings.baseline==1864266&&restored.message_.find("fehlgeschlagen")!=std::string::npos);
 restored.pending_=restored.settings_;restored.pending_alignment_=restored.alignment_;restored.pending_warning_after_=900;restored.runtime_preference_.fail_next=true;restored.apply_save_();assert(restored.runtime_.warning_after==600&&restored.message_.find("Warnschwelle")!=std::string::npos);restored.apply_save_();assert(restored.runtime_.warning_after==900&&restored.message_=="Gespeichert");
 const std::string log="[I] Result: VALID (Raw: 01864266, Conf: 0.980, [0.992, 0.992, 0.992, 0.973, 0.934, 0.992, 0.996, 0.969])";
 restored.capture_digit_log_("meter_reader_tflite",log.data(),log.size());assert(restored.confidence_digits_=="01864266"&&std::abs(restored.digit_confidences_[4]-93.4f)<.01f);
 restored.confidence_digits_.clear();const std::string malformed="Result: VALID (Raw: 01864266, Conf: 0.980, [0.992])";restored.capture_digit_log_("meter_reader_tflite",malformed.data(),malformed.size());assert(restored.confidence_digits_.empty());
 restored.runtime_.warning_after=30;restored.have_previous_reading_=true;restored.last_accepted_at_=5000;tick=35000;restored.features_loop_();assert(restored.stale_&&restored.stale.state&&restored.age.state==30);
 restored.last_accepted_at_=tick;tick+=5000;restored.features_loop_();assert(!restored.stale_&&restored.age.state==5);
 restored.busy_=false;restored.confidence_pending_=true;restored.confidence_finished_at_=tick;restored.digits_="01864266";Sensor digit;restored.digit_sensors_[4]=&digit;
 restored.capture_digit_log_("meter_reader_tflite",log.data(),log.size());assert(!restored.confidence_pending_&&std::abs(digit.state-93.4f)<.01f);
 restored.confidence_digits_.clear();restored.confidence_pending_=true;tick+=3001;restored.capture_digit_log_("meter_reader_tflite",log.data(),log.size());assert(restored.confidence_digits_.empty());
 mqtt::client.messages.clear();restored.mqtt_discovered_=false;restored.mqtt_discovery_index_=0;restored.mqtt_state_at_=0;restored.busy_=false;restored.test_=false;restored.inference_jpeg_=std::shared_ptr<uint8_t>(new uint8_t[4]{255,216,0,217},std::default_delete<uint8_t[]>());restored.inference_jpeg_size_=4;restored.inference_capture_epoch_=1791805539;restored.mqtt_loop_();assert(mqtt::client.messages.size()==3);
 assert(annotation_count==1&&annotated_capture==1791805539);JsonDocument discovery;deserializeJson(discovery,mqtt::client.messages[0].payload);assert(discovery["device"]["identifiers"]=="112233aabbcc"&&discovery["topic"]=="test/camera/image"&&discovery["availability_topic"]=="test/status");assert(mqtt::client.messages[2].payload.size()==4&&mqtt::client.messages[2].payload[2]==0&&mqtt::client.messages[2].retain);
 for(int i=0;i<18;i++)restored.mqtt_loop_();assert(restored.mqtt_discovered_&&restored.mqtt_discovery_index_==19&&mqtt::client.messages.size()==21);
 for(int i=3;i<21;i++){JsonDocument d;deserializeJson(d,mqtt::client.messages[i].payload);assert(d["state_topic"]=="test/meter/state"&&d["device"]["identifiers"]=="112233aabbcc");}
 JsonDocument state;deserializeJson(state,mqtt::client.messages[1].payload);assert(state["confidence_5"].as<float>()>93&&state["value"].isNull());
 restored.mqtt_loop_();assert(mqtt::client.messages.size()==21);restored.test_=true;++restored.preview_sequence_;restored.mqtt_loop_();assert(mqtt::client.messages.size()==21);restored.test_=false;mqtt::client.success=false;restored.mqtt_loop_();assert(restored.mqtt_image_sequence_==1);mqtt::client.success=true;restored.mqtt_loop_();assert(mqtt::client.messages.size()==22);
 mqtt::client.connected=false;restored.mqtt_loop_();assert(restored.mqtt_discovery_index_==0&&!restored.mqtt_discovered_);mqtt::client.connected=true;restored.mqtt_loop_();assert(restored.mqtt_discovery_index_==1);
 JsonDocument old_backup;deserializeJson(old_backup,original.export_json_);old_backup.remove("autofocus_before_reading");MeterSetup legacy;serializeJson(old_backup,legacy.pending_import_);legacy.import_config_();assert(legacy.config_revision_==1&&legacy.autofocus_settings_.before_reading==1);
 MeterSetup failed_focus_save;failed_focus_save.pending_import_=original.export_json_;failed_focus_save.autofocus_preference_.fail_next=true;failed_focus_save.import_config_();assert(failed_focus_save.config_revision_==0&&failed_focus_save.autofocus_settings_.before_reading==1&&failed_focus_save.saved.settings.baseline==0);
 std::cout<<"Features passed: backup/reference roundtrip, strict validation/rollback, per-digit matching, age warning/recovery, camera discovery/MAC, binary JPEG/retain/retry/test isolation\n";
}
'''
include=root/'.esphome/build/wasserzaehler/managed_components/bblanchon__arduinojson/src'
with tempfile.TemporaryDirectory(prefix='meter-features-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-I',str(include),'-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
