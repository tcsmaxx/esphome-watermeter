"""Exercise the production result handler with host fakes (no hardware required)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
cpp = (root / 'components/meter_setup/meter_setup.cpp').read_text()
header = (root / 'components/meter_setup/meter_setup.h').read_text()
settings = header[header.index('struct Settings {'):header.index('class MeterSetup')]
zones = cpp[cpp.index('static std::string zones(const Settings &s) {'):cpp.index('void MeterSetup::setup()')]
handler = cpp[cpp.index('void MeterSetup::result_('):cpp.index('bool MeterSetup::canHandle(')]
validation = cpp[cpp.index('int MeterSetup::invalid_box_('):cpp.index('static std::string zones(const Settings &s) {')]
reset = cpp[cpp.index('void MeterSetup::reset_()'):cpp.index('uint16_t MeterSetup::led_capacity_() const')]
source = r'''
#include <cassert>
#include <mutex>
#include <memory>
#include <string>
#include <vector>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <ctime>
'''+f'#include "{root / "components/meter_setup/reading_guard.h"}"\n'+r'''
using namespace esphome::meter_setup;
uint32_t fake_now=42000;
uint32_t millis() { return fake_now; }
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+settings+r'''
struct Reader {
  bool paused=false;
  std::vector<std::string> zone_updates;
  int arms=0;void arm_for_capture(){++arms;}
  void set_pause_processing(bool p) { paused=p; }
  void set_crop_zones(const std::string &z) { zone_updates.push_back(z); }
};
using AlignedMeterReader=Reader;
struct Value {
  std::vector<float> states;
  void publish_state(float v) { states.push_back(v); }
};
struct Preference { Configuration stored{}; bool save(const Configuration *s) { stored=*s; return true; } };
struct Globals { bool success=true; bool sync() { return success; } } globals;
Globals *global_preferences=&globals;
struct Text {std::vector<std::string> states; void publish_state(const std::string &s){states.push_back(s);} };
struct Binary {bool state=false; void publish_state(bool value){state=value;} };
class MeterSetup {
 public:
  Reader reader; Reader *reader_=&reader;
  Value value; Value *value_=&value;
  Value changes,flows; Value *change_=&changes,*flow_=&flows;
  Text updates,statuses,errors; Text *last_update_=&updates,*status_sensor_=&statuses,*error_sensor_=&errors;
  Binary problem; Binary *problem_=&problem;
  std::string diagnostic_status_,diagnostic_error_{"__initial__"};
  uint32_t last_accepted_at_=0;
  bool have_previous_reading_=false,reading_problem_=false;
  std::string reading_error_,last_reader_log_;
  RecoveryRecord recovery_{};struct RecoveryPref{bool save(RecoveryRecord*){return true;}} recovery_preference_;
  void record_fault_(const std::string&,bool){}
  std::shared_ptr<uint8_t> preview_;size_t preview_size_=0;uint32_t preview_sequence_=0;
  Preference preference_;
  Settings settings_{},pending_{}; AlignmentReference alignment_{},draft_alignment_{},pending_alignment_{},active_alignment_{};std::shared_ptr<unsigned char> reference_capture_;std::string alignment_result_;uint32_t alignment_ms_=0;
  std::mutex mutex_;
  bool inference_started_=true,light_test_=false,capture_pending_=false;IlluminationSettings pending_illumination_{};
  bool lamp=true;void set_illumination_(bool on,const IlluminationSettings&){lamp=on;}
  void reset_illumination_(){}
  bool busy_=true,test_=true,timed_out_=false,accepted_=false,paused_=false;
  uint32_t next_=0,reset_count_=0;
  std::string digits_,message_;
  float confidence_=0;
  static int invalid_box_(const Settings &s);
  static bool valid_(const Settings &s);
  void diagnostics_();
  void reset_();
  bool save_configuration_(const Settings &,const AlignmentReference &,bool);
  void result_(const std::string &s);
};
'''+cpp[cpp.index('bool MeterSetup::save_configuration_('):cpp.index('bool MeterSetup::capture_references_()')]+zones+handler+reset+validation+r'''
int main() {
  MeterSetup camera_failure;camera_failure.test_=false;camera_failure.settings_.baseline=1864266;
  camera_failure.result_("CRITICAL: Camera Frame Failure (Timeout 5000ms)");
  assert(!camera_failure.busy_ && !camera_failure.inference_started_ && camera_failure.reader.paused);
  assert(camera_failure.reader.arms==1 && camera_failure.reading_problem_ && !camera_failure.lamp);
  assert(camera_failure.settings_.baseline==1864266 && camera_failure.value.states.empty());
  Settings overlap;
  for(int i=0;i<8;i++){auto &b=overlap.boxes[i];b[0]=20+i*40;b[1]=100;b[2]=b[0]+45;b[3]=160;}
  assert(MeterSetup::valid_(overlap)); // Adjacent crops overlap by 5 pixels.
  Settings reversed=overlap;reversed.boxes[2][0]=10;reversed.boxes[2][2]=55;
  assert(!MeterSetup::valid_(reversed) && MeterSetup::invalid_box_(reversed)==2);
  Settings outside=overlap;outside.boxes[7][3]=481;assert(!MeterSetup::valid_(outside));
  Settings empty=overlap;empty.boxes[0][2]=empty.boxes[0][0];assert(!MeterSetup::valid_(empty));
  Settings interval=overlap;interval.interval=9;assert(!MeterSetup::valid_(interval));
  const std::string low="Reading: 01004208 -> 1004208.0 (valid: yes, confidence: 60.3%, threshold: 90.0%)";
  const std::string high="Reading: 00123456 -> 123456.0 (valid: yes, confidence: 98.0%, threshold: 90.0%)";
  MeterSetup unsaved;
  unsaved.result_(low);
  assert(unsaved.reader.zone_updates.empty()); // Keep the active test ROIs; no empty restore.
  assert(unsaved.reader.paused && !unsaved.busy_ && !unsaved.lamp);
  assert(unsaved.digits_=="01004208" && unsaved.value.states.empty());
  MeterSetup saved;
  saved.settings_.calibrated=1;
  for(int i=0;i<8;i++){auto &b=saved.settings_.boxes[i];b[0]=i*40;b[1]=100;b[2]=i*40+30;b[3]=160;}
  saved.result_(high);
  assert(saved.reader.zone_updates.size()==1);
  assert(saved.reader.zone_updates[0].find("[0,0,0,0]")==std::string::npos);
  assert(saved.value.states.empty()); // Even a good test never publishes to HA.
  MeterSetup regular;
  regular.test_=false;regular.settings_.calibrated=1;regular.settings_.baseline=123450;
  regular.result_(high);
  assert(regular.accepted_ && regular.settings_.baseline==123456 && !regular.lamp);
  assert(regular.value.states.size()==1 && std::abs(regular.value.states[0]-123.456f)<0.001f);
  assert(regular.reader.zone_updates.empty());
  MeterSetup uncertain;
  uncertain.test_=false;uncertain.settings_.baseline=1004200;
  uncertain.result_(low);
  assert(!uncertain.lamp);
  MeterSetup preview;preview.light_test_=true;preview.result_(high);assert(preview.lamp);
  assert(!uncertain.accepted_ && uncertain.settings_.baseline==1004200 && uncertain.value.states.empty());
  MeterSetup jump;
  jump.test_=false;jump.settings_.baseline=186426;
  jump.result_("Reading: 01864266 -> 1864266.0 (valid: yes, confidence: 90.3%, threshold: 90.0%)");
  assert(!jump.accepted_ && jump.message_.find("Sprung zu groß")!=std::string::npos && jump.value.states.empty());
  MeterSetup good;
  good.test_=false;good.settings_.baseline=1864266;
  good.result_("Reading: 01864266 -> 1864266.0 (valid: yes, confidence: 90.3%, threshold: 90.0%)");
  assert(good.accepted_ && good.value.states.size()==1);
  const std::string stamp=good.updates.states.back();
  assert(stamp.size()==19 && stamp[2]=='.' && stamp[5]=='.' && stamp[10]==' ' && stamp[13]==':' && stamp[16]==':');
  assert(good.changes.states.back()==0 && std::isnan(good.flows.states.back()));
  fake_now+=60000;
  good.result_("Reading: 01864267 -> 1864267.0 (valid: yes, confidence: 98.0%, threshold: 90.0%)"); // idle callbacks ignored
  assert(good.flows.states.size()==1);
  good.busy_=true;
  good.result_("Reading: 01864267 -> 1864267.0 (valid: yes, confidence: 98.0%, threshold: 90.0%)");
  assert(std::abs(good.changes.states.back()-0.001f)<0.000001f);
  assert(std::abs(good.flows.states.back()-0.06f)<0.000001f);
  const auto readings=good.value.states.size(),updates=good.updates.states.size();
  good.busy_=true;good.result_(low);
  assert(good.value.states.size()==readings && good.updates.states.size()==updates && good.reading_problem_);
  good.settings_.calibrated=1;good.diagnostics_();
  assert(good.problem.state && good.statuses.states.back()=="Ablesung abgewiesen");
  regular.settings_.calibrated=1;regular.diagnostics_();assert(!regular.problem.state && regular.errors.states.back()=="Kein Fehler");
  assert(saved.changes.states.empty() && saved.flows.states.empty() && saved.updates.states.empty());
  assert(uncertain.message_.find("KI-Erkennung unsicher")!=std::string::npos);
  // Persist the complete reference/configuration blob; disabling retains reusable patterns.
  AlignmentReference reference;reference.enabled=reference.ready=1;reference.regions[0][0]=120;reference.pixels[1][42]=213;
  good.alignment_=reference;assert(good.save_configuration_(good.settings_,reference,true));
  assert(good.preference_.stored.settings.baseline==1864267 && good.preference_.stored.alignment.enabled && good.preference_.stored.alignment.pixels[1][42]==213);
  reference.enabled=0;assert(good.save_configuration_(good.settings_,reference,true));assert(!good.preference_.stored.alignment.enabled && good.preference_.stored.alignment.ready && good.preference_.stored.alignment.pixels[1][42]==213);
  MeterSetup cleared;
  cleared.alignment_.enabled=cleared.alignment_.ready=1;cleared.alignment_.pixels[1][42]=213;cleared.settings_.calibrated=1;cleared.settings_.baseline=123456;cleared.settings_.boxes[0][2]=10;
  cleared.reset_();
  assert(cleared.paused_ && !cleared.settings_.calibrated && cleared.settings_.baseline==0);
  assert(cleared.settings_.boxes[0][2]==0 && cleared.preference_.stored.settings.calibrated==0);
  assert(!cleared.preference_.stored.alignment.ready && cleared.preference_.stored.alignment.pixels[1][42]==0);
  assert(cleared.reader.paused && cleared.reader.zone_updates.back()=="[]");
  assert(std::isnan(cleared.value.states.back()) && cleared.reset_count_==1);
  MeterSetup failed;
  failed.settings_.calibrated=1;failed.settings_.baseline=123456;
  globals.success=false;failed.reset_();
  assert(failed.settings_.calibrated && failed.settings_.baseline==123456 && failed.reset_count_==0);
  assert(failed.preference_.stored.settings.baseline==123456 && failed.value.states.empty());
  std::cout<<"Result flow tests passed: unsaved/saved ROI restore, test isolation, publish/reject, persistent reset and rollback\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-result-test-') as directory:
    binary = str(Path(directory) / 'result-test')
    subprocess.run(['g++', '-std=c++17', '-x', 'c++', '-', '-o', binary], input=source, text=True, check=True)
    subprocess.run([binary], check=True)
