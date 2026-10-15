"""Exercise actual preference migration and reload; reset must not resurrect legacy data."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
header=(root/'components/meter_setup/meter_setup.h').read_text()
settings=header[header.index('struct Settings {'):header.index('class MeterSetup')]
load=cpp[cpp.index('  preference_=global_preferences->make_preference<Configuration>'):cpp.index('  illumination_preference_=global_preferences->make_preference<IlluminationSettings>')]
save=cpp[cpp.index('bool MeterSetup::save_configuration_('):cpp.index('bool MeterSetup::capture_references_()')]
validation=cpp[cpp.index('int MeterSetup::invalid_box_('):cpp.index('static std::string zones(const Settings &s) {')]
source=r'''
#include <cassert>
#include <map>
#include <vector>
#include <string>
#include <iostream>
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+settings+r'''
std::map<uint32_t,std::vector<uint8_t>> storage;
struct Preference {
 uint32_t key=0;
 template<class T>bool load(T *out){auto it=storage.find(key);if(it==storage.end()||it->second.size()!=sizeof(T))return false;std::memcpy(out,it->second.data(),sizeof(T));return true;}
 template<class T>bool save(const T *in){auto bytes=reinterpret_cast<const uint8_t*>(in);storage[key]=std::vector<uint8_t>(bytes,bytes+sizeof(T));return true;}
};
struct Globals{template<class T>Preference make_preference(uint32_t key){return Preference{key};}bool sync(){return true;}} globals;
Globals *global_preferences=&globals;
struct Reader {std::string crops;void set_crop_zones(const std::string&s){crops=s;}};
std::string zones(const Settings&){return "loaded boxes";}
class MeterSetup {
 public:Preference preference_;Settings settings_{};AlignmentReference alignment_{},draft_alignment_{};bool paused_=true,reading_problem_=false;std::string message_,reading_error_;Reader reader;Reader *reader_=&reader;
 static int invalid_box_(const Settings&);static bool valid_(const Settings&);static bool valid_draft_(const Settings&);
 bool save_configuration_(const Settings&,const AlignmentReference&,bool);
 void load_(){
'''+load+r'''
 }
};
'''+save+validation+r'''
int main(){
 Settings old;old.calibrated=1;old.baseline=1864266;for(int i=0;i<8;i++){old.boxes[i][0]=100+i*40;old.boxes[i][1]=100;old.boxes[i][2]=130+i*40;old.boxes[i][3]=150;}
 globals.make_preference<Settings>(0x7a32b901).save(&old);
 MeterSetup migrated;migrated.load_();assert(migrated.settings_.baseline==1864266&&!migrated.paused_&&!migrated.alignment_.enabled);assert(storage.count(0x7a32b903));
 AlignmentReference refs;refs.enabled=refs.ready=1;uint16_t boxes[2][4]={{120,210,152,242},{480,210,512,242}};memcpy(refs.regions,boxes,sizeof(boxes));refs.pixels[1][42]=213;
 assert(migrated.save_configuration_(old,refs,true));MeterSetup reboot;reboot.load_();assert(!reboot.paused_&&reboot.settings_.baseline==old.baseline&&reboot.alignment_.pixels[1][42]==213&&reboot.draft_alignment_.ready);
 assert(reboot.save_configuration_(Settings{},AlignmentReference{},true));MeterSetup cleared;cleared.load_();assert(!cleared.settings_.calibrated&&cleared.paused_&&!cleared.alignment_.ready&&cleared.settings_.baseline==0); // Legacy key still exists but cannot resurrect after reset.
 refs.ready=0;migrated.save_configuration_(old,refs,true);MeterSetup corrupt;corrupt.load_();assert(corrupt.paused_&&corrupt.reading_problem_&&!corrupt.reading_error_.empty());
 Settings draft;draft.interval=120;draft.boxes[0][0]=10;draft.boxes[0][1]=20;draft.boxes[0][2]=40;draft.boxes[0][3]=60;migrated.save_configuration_(draft,AlignmentReference{},true);MeterSetup partial;partial.load_();assert(partial.paused_&&!partial.settings_.calibrated&&partial.settings_.interval==120&&partial.settings_.boxes[0][0]==10);
 std::cout<<"Persistence passed: legacy migration, reference reload, persistent reset without resurrection, invalid-reference pause\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-persistence-') as temp:
 binary=str(Path(temp)/'test')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
