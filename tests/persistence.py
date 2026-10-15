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
 LegacySettings old;old.calibrated=1;old.baseline=1864266;for(int i=0;i<8;i++){old.boxes[i][0]=100+i*40;old.boxes[i][1]=100;old.boxes[i][2]=130+i*40;old.boxes[i][3]=150;}
 globals.make_preference<LegacySettings>(0x7a32b901).save(&old);
 MeterSetup migrated;migrated.load_();assert(migrated.settings_.baseline==1864266&&migrated.settings_.digit_count==8&&!migrated.paused_);assert(storage.count(0x7a32b90b));
 AlignmentReference refs;refs.enabled=refs.ready=1;uint16_t boxes[2][4]={{120,210,152,242},{480,210,512,242}};memcpy(refs.regions,boxes,sizeof(boxes));refs.pixels[1][42]=213;
 auto current=upgrade_settings(old);assert(migrated.save_configuration_(current,refs,true));MeterSetup reboot;reboot.load_();assert(!reboot.paused_&&reboot.settings_.baseline==old.baseline&&reboot.alignment_.pixels[1][42]==213&&reboot.draft_alignment_.ready);
 assert(reboot.save_configuration_(Settings{},AlignmentReference{},true));MeterSetup cleared;cleared.load_();assert(!cleared.settings_.calibrated&&cleared.paused_&&!cleared.alignment_.ready&&cleared.settings_.baseline==0);
 refs.ready=0;migrated.save_configuration_(current,refs,true);MeterSetup corrupt;corrupt.load_();assert(corrupt.paused_&&corrupt.reading_problem_);
 Settings draft;draft.interval=120;draft.digit_count=6;draft.boxes[0][0]=10;draft.boxes[0][1]=20;draft.boxes[0][2]=40;draft.boxes[0][3]=60;migrated.save_configuration_(draft,AlignmentReference{},true);MeterSetup partial;partial.load_();assert(partial.paused_&&partial.settings_.digit_count==6&&partial.settings_.boxes[0][0]==10);
 static_assert(sizeof(LegacySettings)==84);static_assert(sizeof(LegacyConfiguration)==624);
 LegacyConfiguration prior;prior.settings=old;prior.settings.rotation_tenths=-123;prior.alignment=refs;prior.alignment.ready=1;prior.alignment.rotation_tenths=-123;
 storage.erase(0x7a32b90b);globals.make_preference<LegacyConfiguration>(0x7a32b903).save(&prior);MeterSetup from_v2;from_v2.load_();assert(!from_v2.paused_&&from_v2.settings_.digit_count==8&&from_v2.settings_.rotation_tenths==-123&&from_v2.alignment_.pixels[1][42]==213);
 prior.version=1;prior.settings.rotation_tenths=12345;prior.alignment.rotation_tenths=-23456;storage.erase(0x7a32b90b);globals.make_preference<LegacyConfiguration>(0x7a32b903).save(&prior);MeterSetup padding;padding.load_();assert(!padding.paused_&&padding.settings_.rotation_tenths==0&&padding.alignment_.rotation_tenths==0);
 current.rotation_tenths=-123;refs.rotation_tenths=-123;refs.ready=1;
 migrated.save_configuration_(current,refs,true);MeterSetup angle;angle.load_();assert(!angle.paused_&&angle.settings_.rotation_tenths==-123);
 refs.rotation_tenths=0;migrated.save_configuration_(current,refs,true);MeterSetup mismatch;mismatch.load_();assert(mismatch.paused_&&mismatch.reading_problem_);
 for(int count=1;count<=9;count++){Settings n;n.digit_count=count;n.decimals=0;n.baseline=maximum_reading(count);n.calibrated=1;for(int i=0;i<count;i++){n.boxes[i][0]=10+i*50;n.boxes[i][1]=10;n.boxes[i][2]=40+i*50;n.boxes[i][3]=50;}assert(MeterSetup::valid_(n));assert(migrated.save_configuration_(n,AlignmentReference{},true));MeterSetup changed;changed.load_();assert(!changed.paused_&&changed.settings_.digit_count==count&&changed.settings_.baseline==maximum_reading(count));n.baseline++;assert(!MeterSetup::valid_(n));}
 migrated.save_configuration_(Settings{},AlignmentReference{},true);MeterSetup reset;reset.load_();assert(!reset.settings_.calibrated&&reset.settings_.digit_count==8&&reset.settings_.baseline==0);
 std::cout<<"Persistence passed: all legacy formats, rotation/references, 1..9 digits, drafts and persistent reset without resurrection\n";
}

'''
with tempfile.TemporaryDirectory(prefix='meter-persistence-') as temp:
 binary=str(Path(temp)/'test')
 subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True)
 subprocess.run([binary],check=True)
