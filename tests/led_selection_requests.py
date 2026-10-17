"""Exercise actual options and light HTTP parsing with 64-bit LED selections."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
flow=(root/'components/meter_setup/settings_flow.cpp').read_text()
header=(root/'components/meter_setup/meter_setup.h').read_text()
structs=header[header.index('struct LegacyIlluminationSettings {'):header.index('class MeterSetup;')]
options=flow[flow.index('bool MeterSetup::parse_image_options_('):flow.index('bool MeterSetup::save_all_()')]
a=cpp.index('  if(url=="/meter/light_on"');b=cpp.index('\n  }',a)+4;light=cpp[a:b]
source=r'''
#include <cassert>
#include <cstdlib>
#include <map>
#include <string>
#include <iostream>
'''+f'#include "{root / "components/meter_setup/image_settings.h"}"\n#include "{root / "components/meter_setup/led_selection.h"}"\nusing namespace esphome::meter_setup;\n'+structs+r'''
struct Param{std::string data;const std::string &value(){return data;}};
struct AsyncWebServerRequest {std::map<std::string,Param> values;int status=0;bool hasParam(const char*k){return values.count(k);}Param *getParam(const char*k){return &values.at(k);}void send(int code,const char*,const char*){status=code;}};
struct MeterSetup{ImageLimits image_limits_{5,3,4};ImageSettings image_settings_{},pending_image_{};bool parse_image_options_(AsyncWebServerRequest*);void *illumination_=this;IlluminationSettings illumination_settings_{},pending_illumination_{};bool pending_manual_focus_=false,pending_autofocus_=true,pending_standby_=false,pending_weak_drive_=false;uint16_t pending_focus_position_=0;enum {NONE,LIGHT_ON,LIGHT_OFF,LIGHT_SAVE};int command_=NONE;uint16_t led_capacity_(){return 64;}bool parse_options_(AsyncWebServerRequest*,bool);void request(AsyncWebServerRequest*r,const std::string&url){
'''+light+r'''
}};
'''+options+r'''
AsyncWebServerRequest form(const std::string &mask){AsyncWebServerRequest r;for(const auto &item:std::map<std::string,std::string>{{"focus_mode","auto"},{"position","512"},{"enabled","1"},{"led_count","64"},{"brightness","30"},{"settle_ms","1000"},{"standby","1"},{"weak_drive","0"},{"led_mask",mask}})r.values[item.first]={item.second};return r;}
int main(){MeterSetup owner;
 for(auto mask:{"8000000000000001","0000000000000000","ffffffffffffffff"}){auto r=form(mask);assert(owner.parse_options_(&r,true));assert(format_led_mask(owner.pending_illumination_.led_mask)==mask);owner.request(&r,"/meter/light_on");assert(r.status==200&&owner.command_==owner.LIGHT_ON&&format_led_mask(owner.pending_illumination_.led_mask)==mask);}
 for(auto mask:{"","fff","fffffffffffffffff","fffffffffffffffz"}){auto r=form(mask);auto previous=owner.pending_illumination_.led_mask;assert(!owner.parse_options_(&r,true)&&r.status==400&&owner.pending_illumination_.led_mask==previous);owner.command_=owner.NONE;owner.request(&r,"/meter/light_on");assert(r.status==400&&owner.command_==owner.NONE);}
 auto legacy=form("");legacy.values.erase("led_mask");owner.illumination_settings_.led_mask=0x81;assert(owner.parse_options_(&legacy,false)&&owner.pending_illumination_.led_mask==0x81);owner.request(&legacy,"/meter/light_on");assert(legacy.status==200&&owner.pending_illumination_.led_mask==0x81);
 std::cout<<"LED HTTP parsing passed: 64-bit selections, all-off, missing legacy field, malformed input rejected without mutation\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-led-requests-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
