"""Exercise the production LED mask: surplus slots must stay dark, including after shrink."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text()
apply=cpp[cpp.index('void CountedWhiteEffect::apply('):cpp.index('static std::string zones(const Settings &s);')]
source=r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <iostream>
struct Color {uint32_t raw;Color(int r=0,int g=0,int b=0,int w=0):raw((r<<24)|(g<<16)|(b<<8)|w){}bool operator==(const Color&v){return raw==v.raw;}};
namespace light {
struct AddressableLight {std::vector<Color> pixels=std::vector<Color>(64);int shows=0;int size()const{return pixels.size();}Color &operator[](int i){return pixels[i];}void schedule_show(){++shows;}};
struct Values {float brightness=.3;float get_brightness()const{return brightness;}};
struct State {Values current_values;};
}
struct MeterSetup {uint16_t count=8;uint16_t get_active_led_count()const{return count;}};
struct CountedWhiteEffect {MeterSetup *owner_;light::State *state_;bool initial_=true;uint16_t last_count_=0;float last_brightness_=-1;Color last_color_{};void apply(light::AddressableLight&,const Color&);};
'''+apply+r'''
int main(){
 MeterSetup owner;light::State state;light::AddressableLight strip;CountedWhiteEffect effect{&owner,&state};Color white(0,0,0,255);
 effect.apply(strip,white);assert(strip.shows==1);for(int i=0;i<64;i++)assert(strip[i].raw==(i<8?255u:0u));
 effect.apply(strip,white);assert(strip.shows==1); // No redundant transfers at unchanged brightness.
 owner.count=3;effect.apply(strip,white);assert(strip.shows==2);for(int i=0;i<64;i++)assert(strip[i].raw==(i<3?255u:0u));
 owner.count=64;effect.apply(strip,white);for(auto pixel:strip.pixels)assert(pixel.raw==255);
 state.current_values.brightness=.6;effect.apply(strip,white);assert(strip.shows==4); // Brightness changes rewrite corrected pixels.
 effect.initial_=true;effect.apply(strip,white);assert(strip.shows==5); // Turning on again always repaints.
 std::cout<<"LED count effect passed: exact prefix, excess dark after shrink, full capacity, brightness/restart refresh, unchanged-state suppression\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-led-count-') as temp:
 binary=str(Path(temp)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
