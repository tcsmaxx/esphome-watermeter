"""Validate production image HTTP options, including legacy callers."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
fixture=root/'tests/led_selection_requests.py';scope={'__file__':str(fixture)}
exec(fixture.read_text().split('with tempfile.TemporaryDirectory(')[0],scope)
source=scope['source'];source=source[:source.index('int main()')]+r'''
int main(){MeterSetup owner;owner.image_settings_.exposure=-1;
 auto legacy=form("ffffffffffffffff");assert(owner.parse_image_options_(&legacy)&&owner.pending_image_.exposure==-1);
 for(int wb=0;wb<=4;wb++)for(int e=-5;e<=5;e++)for(int c=-3;c<=3;c++)for(int sat=-4;sat<=4;sat++){
  auto r=form("ffffffffffffffff");r.values["image_exposure"]={std::to_string(e)};r.values["image_contrast"]={std::to_string(c)};r.values["image_saturation"]={std::to_string(sat)};r.values["image_white_balance"]={std::to_string(wb)};
  assert(owner.parse_options_(&r,true)&&owner.pending_image_.exposure==e&&owner.pending_image_.contrast==c&&owner.pending_image_.saturation==sat&&owner.pending_image_.white_balance==wb);
 }
 auto valid=form("ffffffffffffffff");for(auto key:{"image_exposure","image_contrast","image_saturation","image_white_balance"})valid.values[key]={"0"};
 for(auto key:{"image_exposure","image_contrast","image_saturation","image_white_balance"}){
  for(auto value:{"","-6","3.0","1e0","256"," 1","-0","6"}){auto r=valid;r.values[key]={value};auto before=owner.pending_image_;assert(!owner.parse_options_(&r,true)&&r.status==400&&owner.pending_image_==before);}
  auto r=valid;r.values.erase(key);assert(!owner.parse_image_options_(&r)&&r.status==400);
 }
 owner.image_limits_={2,2,2};auto smaller=valid;smaller.values["image_exposure"]={"3"};assert(!owner.parse_image_options_(&smaller));smaller=valid;smaller.values["image_contrast"]={"3"};assert(!owner.parse_image_options_(&smaller));
 std::cout<<"Image options passed: every valid level/mode, missing legacy group, incomplete groups, invalid numbers and no mutation on rejection\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-image-options-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
