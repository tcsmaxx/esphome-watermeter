"""Production reference capture: explicit results, per-region contrast and previous-draft preservation."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
fixture=root/'tests/alignment_flow.py';scope={'__file__':str(fixture)}
exec(fixture.read_text().split('with tempfile.TemporaryDirectory(')[0],scope)
source=scope['source'];source=source[:source.index('int main()')]
source=source.replace(' Settings settings_{},pending_{};', ''' AlignmentReference pending_alignment_{},draft_alignment_{};std::shared_ptr<uint8_t> reference_capture_;size_t reference_capture_size_=0;uint32_t reference_attempt_=0,reference_revision_=0,pending_reference_id_=777,reference_request_id_=0;bool reference_ok_=false;float reference_contrast_[2]{};std::string reference_message_;bool capture_references_();
 Settings settings_{},pending_{};''')
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();source+='namespace esphome::meter_setup {\n'+cpp[cpp.index('bool MeterSetup::capture_references_()'):cpp.index('static std::string quote(')]+'}\n'
source+=r'''
int main(){using namespace esphome::meter_setup;
 MeterSetup owner;owner.pending_alignment_.enabled=1;uint16_t regions[2][4]={{100,200,132,232},{400,200,432,232}};memcpy(owner.pending_alignment_.regions,regions,sizeof(regions));
 std::vector<uint8_t> pixels(640*480*3);std::mt19937 random(55);for(auto &v:pixels)v=random()%256;
 const auto take=[&](){owner.reference_capture_=std::shared_ptr<uint8_t>(static_cast<uint8_t*>(malloc(pixels.size())),free);memcpy(owner.reference_capture_.get(),pixels.data(),pixels.size());owner.reference_capture_size_=pixels.size();return owner.capture_references_();};
 assert(take()&&owner.reference_ok_&&owner.reference_request_id_==777&&owner.reference_attempt_==1&&owner.reference_revision_==1&&owner.draft_alignment_.ready);assert(!owner.reference_capture_&&owner.reference_capture_size_==0);auto previous=owner.draft_alignment_;
 const auto blank=[&](int which){auto &b=regions[which];for(int y=b[1];y<b[3];y++)for(int x=b[0];x<b[2];x++)for(int c=0;c<3;c++)pixels[(y*640+x)*3+c]=100;};
 blank(0);assert(!take()&&!owner.reference_ok_&&owner.reference_attempt_==2&&owner.reference_revision_==1);assert(owner.reference_message_.find("Referenz 1 hat")!=std::string::npos&&owner.reference_contrast_[0]<8&&owner.reference_contrast_[1]>=8);assert(memcmp(&previous,&owner.draft_alignment_,sizeof(previous))==0);
 for(auto &v:pixels)v=random()%256;blank(1);assert(!take()&&owner.reference_message_.find("Referenz 2 hat")!=std::string::npos);blank(0);assert(!take()&&owner.reference_message_.find("Referenz 1 und 2")!=std::string::npos);
 owner.reference_capture_size_=0;assert(!owner.capture_references_()&&owner.reference_message_.find("dekodiert")!=std::string::npos&&owner.reference_attempt_==5);assert(memcmp(&previous,&owner.draft_alignment_,sizeof(previous))==0);
 for(auto &v:pixels)v=random()%256;owner.pending_alignment_.rotation_tenths=1800;assert(take()&&owner.reference_attempt_==6&&owner.reference_revision_==2&&owner.draft_alignment_.rotation_tenths==1800);
 AlignmentReference flat=previous;std::vector<uint8_t> gray(640*480,100);assert(!capture_reference(gray.data(),flat)&&!flat.ready);
 std::cout<<"Reference capture passed: explicit attempt/success, both region diagnostics, decode errors, rotated image, previous valid draft retained and fail-closed ready flag\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-reference-capture-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-O2','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
