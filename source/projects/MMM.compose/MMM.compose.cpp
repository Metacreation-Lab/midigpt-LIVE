/// @file
///	@ingroup 	minexamples
///	@copyright	Copyright 2018 The Min-DevKit Authors. All rights reserved.
///	@license	Use of this source code is governed by the MIT License found in the License.md file.

#include "c74_min.h"
#include <vector>
#include <string>
#include <map>
#include <tuple>

//#include <mach-o/dyld.h>

#ifdef __APPLE__
#include "CoreFoundation/CoreFoundation.h"
#define MY_PLUGIN_BUNDLE_IDENTIFIER net.metacreation.MMMcompose
#endif

#include "./MMM_API/src/mmm_api/midi_io.h" // only needed for MIDI input/output
#include "./MMM_API/src/mmm_api/protobuf/midi.pb.h"
#include "./MMM_API/src/mmm_api/protobuf/midi.pb.cc"
#include "./MMM_API/src/mmm_api/sampling/multi_step_sample.h"

std::string ckpt_path = "";
std::string ckpt_name = "paper_bar_4.pt";

using namespace c74::min;
using namespace c74::min::lib;

class MMM_compose : public object<MMM_compose> {
public:
    MIN_DESCRIPTION	{"Generate MIDI notes with machine-learning"};
    MIN_TAGS		{"composition, machine-learning"};
    MIN_AUTHOR		{"MetacretionLab - SFU"};
    MIN_RELATED		{"MMM.compose"};

    inlet<>  input	        { this, "(anything) input"  };
    outlet<> output         { this, "(messages) generated piece" };
    outlet<> error_output    { this, "(list) runtime error messages" };
    outlet<> dump_output	{ this, "(list) retrieved parameters" };

    c74::min::function process = MIN_FUNCTION {
        

        /* ///////////////////////////////////////////////////////////////
        COLLECT OPERATIONS: Here we collect data from the Live set for conditioning the note genaration
        /////////////////////////////////////////////////////////////// */
            
        c74::min::lock lock {m_mutex};
    
        if (args[0]=="clearNotes"){
            if (verbose) cout << "Clearing piece and status" << c74::min::endl;
            piece.Clear();
            status.Clear();
            //if (piece.events_size()) piece.clear_events();
            piece.set_resolution(resolution);
        }
        else if (args[0]=="DONE"){
            if (verbose) cout << "Done for this clip" << c74::min::endl;
        }
        
        /* ///////////////////////////////////////////////////////////////
        TRACKS:
        */
        
        else if (args[0]=="trackNr" && args.size() >= 2){
           trackNr = int(args[1]);
           
            if ( trackNr < piece.tracks_size() && trackNr < status.tracks_size() ) {
               if (verbose) cout <<    "______________________________________________" << c74::min::endl;
               if (verbose) cout <<  "_______________________CHOSEN TRACK: " << trackNr << c74::min::endl;
               track = piece.mutable_tracks(trackNr);
               strack = status.mutable_tracks(trackNr);
               strack->set_track_id(trackNr);
           } else {
               if (verbose) cout << "the track #" << trackNr << " doesn’t exist! - creating tracks " << piece.tracks_size() << " to "  << trackNr << c74::min::endl;
               for (int i=piece.tracks_size(); i<=trackNr; i++){
                   piece.add_tracks();
                   status.add_tracks();
                   if (verbose) cout << "creating track #" << i << c74::min::endl;
               }
               track = piece.mutable_tracks(trackNr);
               strack = status.mutable_tracks(trackNr);
               strack->set_track_id(trackNr);
           }
        }
        
        /* ///////////////////////////////////////////////////////////////
        BARS:
        */
        else if (args[0]=="clearTrack" && (track)){
            if (track->bars_size()) track->clear_bars();
        }
        else  if (args[0]=="barLength" && args.size() >= 2){
            barLength = args[1];
            if (verbose) cout << "Bar length: " << barLength << " quarter notes " << c74::min::endl;
        } else if (args[0]=="nBars" && args.size() >= 2){
            nBars = int(args[1]);
            if ( (track) && ( nBars == track->bars_size() )) {
                if (verbose) cout << "chosen track: " << trackNr << " has " << track->bars_size() << " bars - filling " << nBars << " bars." << c74::min::endl;
            } else if ( (track) && ( nBars < track->bars_size() )) {
                if (verbose) cout << "chosen track: " << trackNr << " has " << track->bars_size() << " bars - filling " << nBars << " first bars." << c74::min::endl;
                if (piece.mutable_tracks(trackNr)->bars_size()) piece.mutable_tracks(trackNr)->clear_bars();
                for (int i=0; i<nBars; i++) piece.mutable_tracks(trackNr)->add_bars()->set_beat_length(barLength);
            } else if ( (track) && ( nBars > track->bars_size() ) ) {
                int nAddedBars = nBars - track->bars_size();
                if (verbose) cout << "not enough bars on track #" << trackNr << " add " << nAddedBars <<  " bars" << c74::min::endl;
                for (int i=0; i<nAddedBars; i++) piece.mutable_tracks(trackNr)->add_bars()->set_beat_length(barLength);
            }
            else if ( !(track)) {
                cerr << "no existing track has been chosen, please choose a track!" << c74::min::endl;
            }else {
                cerr << "no existing track has been chosen, unknown BUG!" << c74::min::endl;
            }
        }
        
        /* ///////////////////////////////////////////////////////////////
        NOTES:
        */
        else if (args[0]=="notes" && args.size() >= 2){
            if (verbose) cout << "number of notes: " << args[1] << c74::min::endl;
            ///TODO: see how to de this properly ? (looking at status strack ?)
             autoignore = !(bool(args[1]));
            if (autoignore) if (verbose) cout << "ignoring track #" << trackNr << c74::min::endl;
        }
        else if (args[0]=="note" && args.size() >= 5){
            midi::Event* event{nullptr};
            int startTime = int(float(args[2])*resolution);
            int endTime = int((float(args[2])+float(args[3]))*resolution);
            int pitch = args[1];
            int velocity = args[4];
            if (verbose) cout << "pitch: " << pitch << c74::min::endl;
            if (verbose) cout << "starttime: " << startTime << c74::min::endl;
            if (verbose) cout << "endtime: " << endTime << c74::min::endl;
            if (verbose) cout << "velocity: " << velocity << c74::min::endl;
           
            // Note On:
            int barNr = int(startTime/(barLength*resolution));
            if (barNr < piece.tracks(trackNr).bars_size()){
                startTime = startTime-barNr*barLength*resolution;
                event = piece.add_events();
                event->set_pitch(pitch);
                event->set_time(startTime);
                event->set_velocity(velocity);
                // put in appropriate bar
                int eventNr = piece.events_size()-1;
                if (verbose) cout << "adding event #" << eventNr << " (note start) to track #" << trackNr << "’s bar #"  << barNr  << " at time "  << startTime <<  c74::min::endl;
                piece.mutable_tracks(trackNr)->mutable_bars(barNr)->add_events(eventNr);
                
                // Note Off:
                barNr = int((endTime-1)/(barLength*resolution));
                if (barNr < piece.tracks(trackNr).bars_size()){
                    endTime = endTime-barNr*barLength*resolution;}
                else {
                    endTime=barLength*resolution;
                    int oldBarNr = barNr;
                    barNr = piece.tracks(trackNr).bars_size()-1;
                    cout << "event #" << eventNr << " (note end) is happening in bar #"  << oldBarNr  << ", clipping to time:  "  << endTime << " in bar #" << barNr <<  c74::min::endl;
                }
                event = piece.add_events();
                event->set_pitch(pitch);
                event->set_time(endTime);
                event->set_velocity(0);
                eventNr++;
                if (verbose) cout << "adding event #" << eventNr << " (note end) to track #" << trackNr << "’s bar #" << barNr << " at time "  << endTime << c74::min::endl;
                piece.mutable_tracks(trackNr)->mutable_bars(barNr)->add_events(eventNr);
                
            }
            else cout << "trying to add event (note start) to track #" << trackNr << "’s bar #"  << barNr  << " while it has only  "  << piece.tracks(trackNr).bars_size() << " bars! - discarding this event" <<  c74::min::endl;

            
        }
        
        /* ///////////////////////////////////////////////////////////////
        STATUS:
        */
        
        else if (args[0]=="bars" && args.size() >= 2){
            if (strack->selected_bars_size()) strack->clear_selected_bars();
            if (verbose) cout << "Generating " << args.size()-1 << " bars in track: " << trackNr << c74::min::endl;
            for (int i=1; i<args.size();i++) {
                strack->add_selected_bars(bool(args[i]));
                //if (bool(args[i])) autoignore=false;
                if (verbose) cout << "Adding " << bool(args[i]) << " for bar " << i << c74::min::endl;
            }
        }
        else if (args[0]=="track_type" && args.size() >= 1){
            strack->set_track_type(int(args[1])+10);
            track->set_type(int(args[1])+10);
            track->set_is_drum(bool(args[1]));
            if (verbose) cout << "Setting track " << trackNr << "’s type: " << args[1] << c74::min::endl;
        } else if (args[0]=="instrument" && args.size() >= 3){
            strack->set_instrument((args[2]=="any") ? "no_drums" : args[2]);
            track->set_instrument(bool((int(args[1])<0)) ? 0 : int(args[1]));
            if (verbose) cout << "Setting track " << trackNr << "’s instrument: " << args[1] << " / " << args[2]  << c74::min::endl;
        } else if (args[0]=="density" && args.size() >= 1){
            strack->set_density(args[1]);
            if (verbose) cout << "Setting track " << trackNr << "’s density: " << args[1] << c74::min::endl;
        } else if (args[0]=="resample" && args.size() >= 1){
            strack->set_resample(bool(args[1]));
            if (verbose) cout << "Setting track " << trackNr << "’s resample: " << args[1] << c74::min::endl;
        } else if (args[0]=="ignore" && args.size() >= 1){
            strack->set_ignore(bool(args[1]));//||autoignore);
            if (verbose) cout << "Setting track " << trackNr << "’s ignore: " << args[1] << c74::min::endl;
        }
        
        else if (args[0]=="get_status"){
            std::string json_string;
            google::protobuf::util::JsonPrintOptions opt;
            opt.add_whitespace = true;
            google::protobuf::util::MessageToJsonString(status, &json_string, opt);
            dump_output("get_status", json_string );
            
        }
        else if (args[0]=="get_sample"){
            std::string json_string;
            google::protobuf::util::JsonPrintOptions opt;
            opt.add_whitespace = true;
            google::protobuf::util::MessageToJsonString(param, &json_string, opt);
            dump_output("get_sample", json_string );
            
        }
            
        

        /* ///////////////////////////////////////////////////////////////
        TRACK OPERATIONS: mechanism to manage changes in Ableton tracks
                          e.g. moving, ading or deleting tracks in Live
        ///////////////////////////////////////////////////////////////

        else if (args[0]=="tracks_changed" && args.size() >= 1){
            nrTracksMoved=0;
            pieceCopy.Clear();
            pieceCopy.set_resolution(resolution);
            pieceCopy.set_tempo(tempo);
            for (auto e : *piece.mutable_events() ) {
                midi::Event* event{};
                event = pieceCopy.add_events();
                event->Swap(&e);
            }
            statusCopy.Clear();
            if (verbose) cout << "Changing tracks " << nrTracksMoved << c74::min::endl;
        } else if (args[0]=="new_track" && args.size() >= 2){
            int newTrackNr = args[1];
            nrTracksMoved++;
            if (verbose) cout << "Creating new track #" << newTrackNr << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
            track = pieceCopy.add_tracks();
            strack = statusCopy.add_tracks();
            strack->set_track_id(trackNr);
        } else if (args[0]=="reorder_track" && args.size() >= 3){
            int trackNr = args[1];
            nrTracksMoved++;
            if (verbose) cout << "Moving existing track #" << trackNr << " to track #" << args[2] << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
            // move track to piece copy
            track = pieceCopy.add_tracks();
            track->Swap(piece.mutable_tracks(trackNr));
            strack = statusCopy.add_tracks();
            strack->set_track_id(args[2]);
            strack->Swap(status.mutable_tracks(trackNr));
        } else if (args[0]=="tracks_done" && args.size() >= 2){
            if (verbose) cout << "Tracks updating, swapping pieces with " << nrTracksMoved << " tracks" << c74::min::endl;
            piece.Clear();
            piece.Swap(&pieceCopy);
            status.Clear();
            status.Swap(&statusCopy);
        }
         
          */
       
        /* ///////////////////////////////////////////////////////////////
                PIECE PARAMETERS:
        /////////////////////////////////////////////////////////////// */
        
        else if (args[0]=="tempo" && args.size() >= 2){
            tempo = args[1];
            piece.set_tempo(tempo);
        } else if (args[0]=="get_piece"){
            std::string json_string;
            google::protobuf::util::JsonPrintOptions opt;
            opt.add_whitespace = true;
            google::protobuf::util::MessageToJsonString(piece, &json_string, opt);
            dump_output("get_piece", json_string );
        } else if (args[0]=="debug" && args.size() >= 2){
            verbose = bool(args[1]);
        } else if (args[0]=="get_version" && args.size() >= 1){
            dump_output("get_version", version_number);
        }
        
        
        
        /* ///////////////////////////////////////////////////////////////
               SAMPLING PARAMETERS:
        /////////////////////////////////////////////////////////////// */
        
        else if (args[0]=="get_instruments"){
            dump_output.send( "get_instruments_generic", int(generic_instruments.size()) );
            for (int i=0; i<generic_instruments.size();i++) {
                dump_output.send( "get_instruments", generic_instruments[i] );
            }
            dump_output.send( "get_instruments_start" );
            for (int i=0; i<128;i++) {
                dump_output.send( "get_instruments", mmm::GM_REV[i] );
            }
            dump_output.send( "get_instruments_done" );
        } else if (args[0]=="tracks_per_step" && args.size() >= 2){
            param.set_tracks_per_step(tracks_per_step = args[1]);
        } else if (args[0]=="bars_per_step" && args.size() >= 2){
            param.set_bars_per_step(bars_per_step = args[1]);
        } else if (args[0]=="model_dim" && args.size() >= 2){
            param.set_model_dim(model_dim = args[1]);
        } else if (args[0]=="shuffle" && args.size() >= 2){
            param.set_shuffle(shuffle = args[1]);
        } else if (args[0]=="percentage" && args.size() >= 2){
            param.set_percentage(percentage = args[1]);
        } else if (args[0]=="temperature" && args.size() >= 2){
            param.set_temperature(temperature = args[1]);
        } else if (args[0]=="batch_size" && args.size() >= 2){
            param.set_batch_size(batch_size = args[1]);
        } else if (args[0]=="model_path" && args.size() >= 2){
            ckpt_name = std::string(args[1]);
            ckpt_path = getModelsPath()+ckpt_name;
            param.set_ckpt(ckpt_path);// = std::string(args[1]));
            if (verbose)
            {cout << "Chosen model path: " << ckpt_path << c74::min::endl;
                dump_output.send( "model_path", ckpt_path );}
        } else if (args[0]=="get_models_folder"){
            dump_output.send( "get_models_folder", getModelsPath() );
        }

        return {};
    };

    /*//////////////////////////////////////////////////////////////////////
    MAX INPUT MANAGEMENT : Here we define behaviours for Max external’s input
    //////////////////////////////////////////////////////////////////////*/
    
    message<threadsafe::yes> list { this, "Messages to MMM compose.", process };
    
    message<threadsafe::yes> anything { this, "anything", "Messages to MMM compose.", process };

    message<threadsafe::yes> bang { this, "bang", "Trigger the generation.",
    MIN_FUNCTION {
        lock  lock {m_mutex};
        
        // set parameters:
        piece.set_resolution(resolution);
        piece.set_tempo(tempo);
        param.set_tracks_per_step(tracks_per_step);
        param.set_bars_per_step(bars_per_step);
        param.set_model_dim(model_dim);
        param.set_shuffle(shuffle);
        param.set_percentage(percentage);
        param.set_temperature(temperature);
        param.set_batch_size(batch_size);
        param.set_polyphony_hard_limit(polyphony_hard_limit);
        param.set_verbose(true);
        param.set_encoder("TRACK_BAR_FILL_DENSITY_ENCODER");
        ckpt_path = getModelsPath()+ckpt_name;
        param.set_ckpt(ckpt_path);
        
        // generate piece   
        try {
            if (verbose) cout << "Generating piece " << c74::min::endl;
            mmm::sample(&piece, &status, &param);
        }
        catch(const std::runtime_error& re) {
            cerr << "Runtime error: " << re.what() << c74::min::endl;
            error_output(re.what());
        }
        
        // format for Max
        int track_num = 0;
        for (const auto track : piece.tracks()) {
            output("track", track_num);
            output("instrument", track.instrument());
            int bar_start_time{0};
            int note_num{0};
            int pitch{0};
            int vel{0};
            float time{0};
            float dur{0};
            std::map<int, std::pair<float, int>> pool;
            for (const auto bar : track.bars()) {
                for (const auto event_index : bar.events()) {
                    const midi::Event e = piece.events(event_index);
                    pitch = e.pitch();
                    time = float(bar_start_time + e.time()) / piece.resolution();
                    vel = e.velocity();
                    if (e.velocity() != 0) {
                        pool[pitch] = {time, vel};
                    } else {
                        time = std::get<0>(pool[pitch]) ;
                        vel  = std::get<1>(pool[pitch]);
                        dur = float(bar_start_time + e.time()) / piece.resolution() - time;
                        if (dur==0) dur = 1;
                        output("note", note_num, pitch, time , dur, vel);
                        note_num++;
                    }
                }
                bar_start_time += bar.beat_length() * piece.resolution();
            }
            output("notes", note_num);
            track_num++;
        }
         
        //output(Gpiece);
            /*
        std::string json_string;
        google::protobuf::util::JsonPrintOptions opt;
        opt.add_whitespace = true;
        google::protobuf::util::MessageToJsonString(piece, &json_string, opt);
        output(json_string);
        lock.unlock();
             */

        //output.send( stuff );
        
        return {};
        }
    };
    
    /*////////////////////////////////////////////////////////////////////////
    MAX INIT MANAGEMENT : Here we define behaviours at Max external’s startup
    ////////////////////////////////////////////////////////////////////////*/

    // post to max window == but only when the class is loaded the first time
    message<> maxclass_setup { this, "maxclass_setup",
        MIN_FUNCTION {
            cout << "MMM compose object by Metacreation lab - SFU " << version_number << c74::min::endl;
            dump_output("get_version", version_number);
            piece.set_resolution(resolution);
            piece.set_tempo(tempo);
            param.set_tracks_per_step(1);
            param.set_bars_per_step(2);
            param.set_model_dim(4);
            param.set_shuffle(false);
            param.set_percentage(100);
            param.set_temperature(1.);
            param.set_batch_size(1);
            param.set_polyphony_hard_limit(5);
            param.set_verbose(false);
            param.set_encoder("TRACK_BAR_FILL_DENSITY_ENCODER");
            ckpt_path = getModelsPath()+"paper_bar_4.pt";
            param.set_ckpt(ckpt_path);
            
            cout << "Bundle path is\n" << getModelsPath() << c74::min::endl;
         
            return {};
        }
    };

/*////////////////////////////////////////////////////////////////////////
PRIVATE MEMBERS : Here we define private members for this class
////////////////////////////////////////////////////////////////////////*/
private:
    atoms m_data; // should go away once all cleaned from Max example
    mutex m_mutex;

    midi::Piece  piece; //,  pieceCopy;
    midi::Status status; //, statusCopy;
    midi::SampleParam    param{};
            
    int32_t resolution{12};
    int32_t tempo{120};
    int32_t tracks_per_step{1};
    int32_t bars_per_step{2};
    int32_t model_dim{4};
    int32_t shuffle{false};
    int32_t percentage{100};
    float temperature{1.};
    int32_t batch_size{1};
    int32_t polyphony_hard_limit{5};
                
    midi::Track* track{nullptr};
    midi::StatusTrack* strack{nullptr};
    int trackNr{0};
    int nBars{0};
    float barLength{0};
            
    bool autoignore{false};
    //int nrTracksMoved{0}; // for operations related to track changes
    bool verbose{false};
                
    std::vector<std::string> generic_instruments {	"any", "piano", "chromatic_perc", "organ", "guitar", "bass", "strings", "ensemble", "brass", "reed", "pipe", "synth_lead", "synth_pad", "synth_effects", "ethnic", "percussive", "sound_fx" };
                
    std::string version_number {"v.0.1b1"};
    //std::string modelsPath;
                
    std::string getModelsPath() {
                    
#ifdef __APPLE__
                    
#define QUOTE(str) #str
#define EXPAND_AND_QUOTE(str) QUOTE(str)
#define MY_PLUGIN_BUNDLE_IDENTIFIER_STRING EXPAND_AND_QUOTE(MY_PLUGIN_BUNDLE_IDENTIFIER)
                    
                    CFBundleRef mainBundle = CFBundleGetBundleWithIdentifier(CFSTR(MY_PLUGIN_BUNDLE_IDENTIFIER_STRING));
                    CFURLRef resourcesURL = CFBundleCopyResourcesDirectoryURL(mainBundle);
                    char path[PATH_MAX];
                    if (!CFURLGetFileSystemRepresentation(resourcesURL, TRUE, (UInt8 *)path, PATH_MAX))
                    {
                        // error!
                    }
                    CFRelease(resourcesURL);
                    
                    std::string modelsPath = strcat(path, "/models/");
                    return modelsPath;
                    
#endif
                };
               
};

MIN_EXTERNAL(MMM_compose);
