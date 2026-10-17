"""Run production backup/import, health, per-digit parsing and MQTT code on the host."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
header=(root/'components/meter_setup/meter_setup.h').read_text();cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();features=(root/'components/meter_setup/features.cpp').read_text()
structs=header[header.index('struct Settings {'):header.index('class MeterSetup;')]
settings_flow=(root/"components/meter_setup/settings_flow.cpp").read_text()
all_save=settings_flow[settings_flow.index("bool MeterSetup::save_all_()"):settings_flow.rfind("\n}")]
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
#define ESP_LOGE(...) ((void)0)
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
'''+f'#include "{root / "components/meter_setup/image_settings.h"}"\n#include "{root / "components/meter_setup/led_selection.h"}"\n#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+structs+r'''
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
 std::string export_json_,pending_import_,message_,reading_error_,confidence_digits_,digits_;float digit_confidences_[9]{},reading_age_=NAN,confidence_=0;
 uint32_t pending_warning_after_=0,next_=0,health_updated_=0,last_accepted_at_=0,boot_started_=0,config_revision_=0,mqtt_image_sequence_=0,preview_sequence_=1;
 std::shared_ptr<uint8_t> preview_,inference_jpeg_;size_t preview_size_=0,inference_jpeg_size_=0;std::time_t inference_capture_epoch_=0;uint32_t timestamped_sequence_=0;
 Sensor changes,flows,value,confidence;Sensor *change_=&changes,*flow_=&flows,*value_=&value,*confidence_sensor_=&confidence,*digit_sensors_[9]{};Text *last_update_=nullptr,*status_sensor_=nullptr,*error_sensor_=nullptr;
 bool confidence_pending_=false;uint32_t confidence_finished_at_=0,mqtt_state_at_=0;uint8_t mqtt_discovery_index_=0;
 Sensor age;Sensor *age_sensor_=&age;Binary stale;Binary *stale_sensor_=&stale;Reader reader;Reader *reader_=&reader;
 struct Power{bool standby=true,weak=false;bool standby_enabled(){return standby;}bool weak_drive(){return weak;}bool configure(bool s,bool w){standby=s;weak=w;return true;}}camera_power_;
 uint32_t save_attempt_=0;bool save_ok_=false,pending_autofocus_=true,pending_manual_focus_=false,pending_standby_=true,pending_weak_drive_=false;uint16_t pending_focus_position_=512;bool save_all_();
 AutofocusSettings autofocus_settings_{};Pref autofocus_preference_;
 ImageSettings image_settings_{},pending_image_{};Pref image_preference_;
 Pref illumination_preference_,runtime_preference_;Configuration saved{};
 uint16_t led_capacity_()const{return 64;}bool save_configuration_(const Settings &s,const AlignmentReference&a,bool){saved.settings=s;saved.alignment=a;return true;}
 void set_illumination_(bool,const IlluminationSettings&){}
 void apply_save_(){
'''+save_body+r'''
 }
 static int invalid_box_(const Settings&);static bool valid_(const Settings&);static bool valid_draft_(const Settings&);
 void capture_digit_scores_(const std::string&,const float*);
 void capture_digit_log_(const char*,const char*,size_t);void features_loop_();void build_export_();void import_config_();void mqtt_loop_();
};
'''+validation+methods+all_save+r'''
int main(){
 MeterSetup original;original.settings_.calibrated=1;original.settings_.rotation_tenths=-123;original.settings_.baseline=1864266;original.runtime_.warning_after=600;original.autofocus_settings_.before_reading=0;original.image_settings_.exposure=-1;original.image_settings_.contrast=1;original.image_settings_.saturation=-1;original.image_settings_.white_balance=3;original.illumination_settings_.led_count=6;original.illumination_settings_.led_mask=0x8000000000000025ULL;
 for(int i=0;i<8;i++){auto &b=original.settings_.boxes[i];b[0]=20+i*50;b[1]=100;b[2]=b[0]+30;b[3]=150;}
 original.alignment_.enabled=original.alignment_.ready=1;uint16_t regions[2][4]={{100,200,132,232},{450,200,482,232}};memcpy(original.alignment_.regions,regions,sizeof(regions));for(auto &row:original.alignment_.pixels)for(int i=0;i<256;i++)row[i]=i%2?20:200;
 original.build_export_();assert(original.export_json_.size()<3000);assert(original.export_json_.find("password")==std::string::npos);
 MeterSetup restored;restored.pending_import_=original.export_json_;restored.import_config_();assert(restored.image_settings_==original.image_settings_&&restored.settings_.baseline==1864266&&restored.runtime_.warning_after==600&&restored.illumination_settings_.led_mask==0x8000000000000025ULL&&restored.illumination_settings_.led_count==6&&restored.paused_&&restored.config_revision_==1&&!restored.autofocus_settings_.before_reading);
 assert(restored.settings_.rotation_tenths==-123&&restored.alignment_.rotation_tenths==-123);
 assert(memcmp(restored.alignment_.pixels,original.alignment_.pixels,sizeof(original.alignment_.pixels))==0&&restored.reader.zones.find("[20,100,50,150]")!=std::string::npos);
 auto corrupt=[&](const char *field,auto value){JsonDocument d;deserializeJson(d,original.export_json_);d[field]=value;std::string data;serializeJson(d,data);restored.pending_import_=data;restored.import_config_();assert(restored.config_revision_==1&&restored.settings_.baseline==1864266&&restored.message_.find("abgelehnt")!=std::string::npos);};
 corrupt("camera_standby",1);corrupt("camera_weak_drive","yes");corrupt("autofocus_before_reading",1);corrupt("version",2);corrupt("camera_width",320);corrupt("warning_after",0);
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
 for(int i=0;i<19;i++)restored.mqtt_loop_();assert(restored.mqtt_discovered_&&restored.mqtt_discovery_index_==20&&mqtt::client.messages.size()==22);
 for(int i=3;i<22;i++){if(mqtt::client.messages[i].payload.empty()){assert(mqtt::client.messages[i].topic.find("confidence_9/config")!=std::string::npos);continue;}JsonDocument d;deserializeJson(d,mqtt::client.messages[i].payload);assert(d["state_topic"]=="test/meter/state"&&d["device"]["identifiers"]=="112233aabbcc");}
 JsonDocument state;deserializeJson(state,mqtt::client.messages[1].payload);assert(state["confidence_5"].as<float>()>93&&state["value"].isNull());
 restored.mqtt_loop_();assert(mqtt::client.messages.size()==22);restored.test_=true;++restored.preview_sequence_;restored.mqtt_loop_();assert(mqtt::client.messages.size()==22);restored.test_=false;mqtt::client.success=false;restored.mqtt_loop_();assert(restored.mqtt_image_sequence_==1);mqtt::client.success=true;restored.mqtt_loop_();assert(mqtt::client.messages.size()==23);
 mqtt::client.connected=false;restored.mqtt_loop_();assert(restored.mqtt_discovery_index_==0&&!restored.mqtt_discovered_);mqtt::client.connected=true;restored.mqtt_loop_();assert(restored.mqtt_discovery_index_==1);
 JsonDocument old_backup;deserializeJson(old_backup,original.export_json_);old_backup["settings"].remove("rotation_tenths");old_backup.remove("autofocus_before_reading");old_backup.remove("manual_focus_enabled");old_backup.remove("manual_focus_position");old_backup.remove("camera_standby");old_backup.remove("camera_weak_drive");MeterSetup legacy;legacy.camera_power_.standby=false;legacy.camera_power_.weak=true;serializeJson(old_backup,legacy.pending_import_);legacy.import_config_();assert(legacy.config_revision_==1&&legacy.settings_.rotation_tenths==0&&legacy.autofocus_settings_.before_reading==1&&!legacy.camera_power_.standby_enabled()&&legacy.camera_power_.weak_drive());
 for(const auto bad_angle:{"1801","-1801","1.5","\"90\"","true"}){JsonDocument d;deserializeJson(d,original.export_json_);d["settings"]["rotation_tenths"]=serialized(bad_angle);MeterSetup bad;serializeJson(d,bad.pending_import_);bad.import_config_();assert(bad.config_revision_==0);}
 MeterSetup failed_focus_save;failed_focus_save.pending_import_=original.export_json_;failed_focus_save.autofocus_preference_.fail_next=true;failed_focus_save.import_config_();assert(failed_focus_save.config_revision_==0&&failed_focus_save.autofocus_settings_.before_reading==1&&failed_focus_save.saved.settings.baseline==0);
 original.autofocus_settings_.manual_enabled=1;original.autofocus_settings_.position=623;original.build_export_();MeterSetup manual_backup;manual_backup.pending_import_=original.export_json_;manual_backup.import_config_();assert(manual_backup.config_revision_==1&&manual_backup.autofocus_settings_.manual_enabled&&manual_backup.autofocus_settings_.position==623);
 JsonDocument invalid_manual;deserializeJson(invalid_manual,original.export_json_);invalid_manual["manual_focus_position"]=1024;MeterSetup rejected_manual;serializeJson(invalid_manual,rejected_manual.pending_import_);rejected_manual.import_config_();assert(rejected_manual.config_revision_==0);
 MeterSetup combined;combined.settings_=original.settings_;combined.pending_=combined.settings_;combined.pending_.interval=180;combined.pending_alignment_=original.alignment_;combined.pending_illumination_=original.illumination_settings_;combined.pending_illumination_.brightness=37;combined.pending_warning_after_=720;combined.pending_autofocus_=false;combined.pending_manual_focus_=true;combined.pending_focus_position_=339;combined.pending_standby_=false;combined.have_previous_reading_=true;combined.runtime_.last_valid_epoch=1700000000;assert(combined.save_all_()&&combined.save_ok_&&combined.save_attempt_==1&&combined.settings_.interval==180&&combined.autofocus_settings_.position==339&&combined.illumination_settings_.brightness==37&&combined.runtime_.warning_after==720&&!combined.camera_power_.standby_enabled());assert(combined.have_previous_reading_&&combined.runtime_.last_valid_epoch==1700000000);
 combined.pending_.interval=240;combined.pending_focus_position_=400;combined.autofocus_preference_.fail_next=true;assert(!combined.save_all_()&&!combined.save_ok_&&combined.save_attempt_==2&&combined.settings_.interval==180&&combined.autofocus_settings_.position==339&&combined.saved.settings.interval==180);assert(combined.message_.find("Fokuseinstellungen")!=std::string::npos);
 combined.image_preference_.fail_next=true;assert(!combined.save_all_()&&!combined.save_ok_&&combined.message_.find("Bildeinstellungen")!=std::string::npos);
 combined.illumination_preference_.fail_next=true;assert(!combined.save_all_()&&!combined.save_ok_&&combined.message_.find("Beleuchtung")!=std::string::npos&&combined.settings_.interval==180);
 for(int count=1;count<=9;count++){
  MeterSetup meter;meter.settings_.digit_count=count;meter.settings_.decimals=0;meter.settings_.baseline=maximum_reading(count);meter.settings_.calibrated=1;
  for(int i=0;i<count;i++){auto &b=meter.settings_.boxes[i];b[0]=10+i*50;b[1]=100;b[2]=40+i*50;b[3]=150;}
  meter.build_export_();MeterSetup copy;copy.pending_import_=meter.export_json_;copy.import_config_();assert(copy.config_revision_==1&&copy.settings_.digit_count==count&&copy.settings_.baseline==maximum_reading(count));
  JsonDocument bad;deserializeJson(bad,meter.export_json_);bad["settings"]["digit_count"]=count==9?8:count+1;MeterSetup reject;serializeJson(bad,reject.pending_import_);reject.import_config_();assert(reject.config_revision_==0);
  std::string log="Result: VALID (Raw: "+std::string(count,'2')+", Conf: 0.99, [";for(int i=0;i<count;i++){if(i)log+=", ";log+="0.99";}log+="])";meter.capture_digit_log_("meter_reader_tflite",log.data(),log.size());assert(meter.confidence_digits_==std::string(count,'2')&&meter.digit_confidences_[count-1]==99.f);
 }
 JsonDocument old_count;deserializeJson(old_count,original.export_json_);old_count["settings"].remove("digit_count");MeterSetup old_layout;serializeJson(old_count,old_layout.pending_import_);old_layout.import_config_();assert(old_layout.config_revision_==1&&old_layout.settings_.digit_count==8);
 JsonDocument old_light;deserializeJson(old_light,original.export_json_);old_light["illumination"].remove("led_mask");MeterSetup old_leds;serializeJson(old_light,old_leds.pending_import_);old_leds.import_config_();assert(old_leds.config_revision_==1&&old_leds.illumination_settings_.led_mask==UINT64_MAX);
 JsonDocument bad_light;deserializeJson(bad_light,original.export_json_);bad_light["illumination"]["led_mask"]="ffffffffffffffff0";MeterSetup bad_leds;serializeJson(bad_light,bad_leds.pending_import_);bad_leds.import_config_();assert(bad_leds.config_revision_==0);bad_light["illumination"]["led_mask"]=123;serializeJson(bad_light,bad_leds.pending_import_);bad_leds.import_config_();assert(bad_leds.config_revision_==0);
 JsonDocument bad_image;deserializeJson(bad_image,original.export_json_);bad_image["image"]["exposure"]=256;MeterSetup invalid_image;serializeJson(bad_image,invalid_image.pending_import_);invalid_image.import_config_();assert(invalid_image.config_revision_==0);
 JsonDocument old_image;deserializeJson(old_image,original.export_json_);old_image.remove("image");MeterSetup legacy_image;legacy_image.image_settings_.contrast=2;serializeJson(old_image,legacy_image.pending_import_);legacy_image.import_config_();assert(legacy_image.config_revision_==1&&legacy_image.image_settings_.contrast==2);
 mqtt::client.messages.clear();MeterSetup fewer;fewer.settings_.digit_count=6;for(int i=0;i<20;i++)fewer.mqtt_loop_();int removed=0;for(const auto &m:mqtt::client.messages)if(m.payload.empty()){assert(m.retain);++removed;}assert(removed==3&&fewer.mqtt_discovered_);
 mqtt::client.messages.clear();MeterSetup more;more.settings_.digit_count=9;for(int i=0;i<20;i++)more.mqtt_loop_();for(const auto &m:mqtt::client.messages)assert(!m.payload.empty());
 MeterSetup resized;resized.settings_.baseline=1864266;resized.settings_.calibrated=1;resized.pending_=resized.settings_;resized.pending_.digit_count=7;resized.pending_.baseline=123456;resized.pending_warning_after_=300;resized.pending_illumination_=resized.illumination_settings_;resized.digits_="01864266";resized.confidence.state=99;resized.have_previous_reading_=true;assert(resized.save_all_()&&resized.digits_.empty()&&!resized.have_previous_reading_&&std::isnan(resized.confidence.state));
 std::cout<<"Features passed: backup/reference roundtrip, strict validation/rollback, per-digit matching, age warning/recovery, camera discovery/MAC, binary JPEG/retain/retry/test isolation\n";
}
'''
include=root/'.esphome/build/wasserzaehler/managed_components/bblanchon__arduinojson/src'
with tempfile.TemporaryDirectory(prefix='meter-features-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-I',str(include),'-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
