"""Exercise the production digit-count save/test request parser and bounds."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();header=(root/'components/meter_setup/meter_setup.h').read_text()
structs=header[header.index('struct Settings {'):header.index('struct AutofocusSettings')]
validation=cpp[cpp.index('int MeterSetup::invalid_box_('):cpp.index('static std::string zones(const Settings &s) {')]
branch=cpp[cpp.index('    Settings candidate=settings_;'):cpp.index('  } else {r->send(404,"text/plain","Unbekannt");return;}')]
source=r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <map>
#include <string>
#include <iostream>
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+structs+r'''
struct Param{std::string text;std::string value(){return text;}};
struct Request{std::map<std::string,Param> params;int code=0;std::string message;bool hasParam(const char*k){return params.count(k);}Param *getParam(const char*k){return &params.at(k);}void send(int c,const char*,const std::string&m){code=c;message=m;}};
struct MeterSetup{Settings settings_,pending_;enum{NONE,SAVE_ALL,SAVE,TEST};int command_=NONE;
 static int invalid_box_(const Settings&);static bool valid_(const Settings&);static bool valid_draft_(const Settings&);
 void parse(Request *r,const std::string &url){
'''+branch+r'''
 }
};
'''+validation+r'''
Request request(int count){Request r;const auto put=[&](const char*k,const std::string&v){r.params[k].text=v;};
 put("digit_count",std::to_string(count));put("decimals","0");put("interval","60");put("max_step","1000");put("baseline",std::string(count,'9'));put("baseline_changed","1");put("baseline_provided","1");std::string boxes;for(int i=0;i<count;i++){if(i)boxes+=',';boxes+=std::to_string(10+i*50)+",100,"+std::to_string(40+i*50)+",150";}put("boxes",boxes);return r;}
int main(){
 for(int n=1;n<=9;n++){MeterSetup m;auto r=request(n);m.parse(&r,"/meter/save_all");assert(r.code==200&&m.command_==MeterSetup::SAVE_ALL&&m.pending_.digit_count==n&&m.pending_.calibrated&&m.pending_.baseline==maximum_reading(n));for(int i=n;i<9;i++)for(auto v:m.pending_.boxes[i])assert(v==0);}
 for(const auto count:{"0","10","-1","1.5","","9x"}){MeterSetup m;auto r=request(8);r.params["digit_count"].text=count;m.parse(&r,"/meter/save_all");assert(r.code==400&&m.command_==0&&m.settings_.digit_count==8);}
 MeterSetup draft;auto empty=request(1);empty.params["baseline"].text="0";empty.params["baseline_provided"].text="0";draft.parse(&empty,"/meter/save_all");assert(empty.code==200&&!draft.pending_.calibrated);
 MeterSetup zero;empty.params["baseline_provided"].text="1";zero.parse(&empty,"/meter/save_all");assert(empty.code==200&&zero.pending_.calibrated&&zero.pending_.baseline==0);
 MeterSetup legacy;auto old=request(8);old.params.erase("digit_count");old.params.erase("baseline_provided");legacy.parse(&old,"/meter/save_all");assert(old.code==200&&legacy.pending_.digit_count==8&&legacy.pending_.calibrated);
 for(const auto key:{"boxes","decimals","baseline"}){MeterSetup m;auto r=request(7);r.params[key].text=std::string(key)=="boxes"?"10,10,20,20":std::string(key)=="decimals"?"7":"9999999999";m.parse(&r,"/meter/save_all");assert(r.code==400&&m.command_==0);}
 MeterSetup test;auto r=request(7);test.parse(&r,"/meter/test");assert(!r.code&&test.command_==MeterSetup::TEST&&test.pending_.digit_count==7);
 std::cout<<"Digit request parser passed: 1..9, exact coordinates, legacy clients, malformed counts, overflow, decimals and empty/zero baseline\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-digit-config-') as temp:
 binary=str(Path(temp)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
