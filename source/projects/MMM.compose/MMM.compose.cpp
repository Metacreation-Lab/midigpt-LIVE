/// @file
///	@ingroup 	minexamples
///	@copyright	Copyright 2018 The Min-DevKit Authors. All rights reserved.
///	@license	Use of this source code is governed by the MIT License found in the License.md file.

#include "c74_min.h"
#include <vector>
#include <string>
#include <map>
#include <tuple>

#include "./MMM_API/src/mmm_api/midi_io.h" // only needed for MIDI input/output
#include "./MMM_API/src/mmm_api/protobuf/midi.pb.h"
#include "./MMM_API/src/mmm_api/protobuf/midi.pb.cc"
#include "./MMM_API/src/mmm_api/sample_internal.h"

std::string ckpt_path = "/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/OPZ_MODELS/opz.pt";

// This is the structure we use to define different models that are used.
// The keys in the map are the number of bars and the model type.
// The values in the map are the encoding class and the ckpt path.
std::map<std::tuple<int,MODEL_TYPE>,std::tuple<ENCODER_TYPE,std::string>> ckpt_map = {
    {{4,TRACK_MODEL},{TE_TRACK_DENSITY_ENCODER,ckpt_path}},
    {{4,BAR_INFILL_MODEL},{TE_TRACK_DENSITY_ENCODER,ckpt_path}}
};

using namespace c74::min;
using namespace c74::min::lib;

class MMM_compose : public object<MMM_compose> {
public:
    MIN_DESCRIPTION	{"Generate MIDI notes with machine-learning"};
    MIN_TAGS		{"composition"};
    MIN_AUTHOR		{"MetacretionLab - SFU"};
    MIN_RELATED		{"MMM.compose"};

    inlet<>  input	{ this, "(anything) input"  };
    outlet<> output	{ this, "(list) result" };
    
    // Available operations
    enum class operations : int { collect, generate, expand, enum_count };
    enum_map operations_range = {"collect", "generate", "expand"};
    attribute<operations> operation { this, "operation", operations::collect, operations_range,
        description {"Choose the operation to perform with the input: collect, generate or expand "}
    };


    c74::min::function process = MIN_FUNCTION {
        
        /*///////////////////////////////////////////////////////////////
        CONTEXTUAL OPERATIONS: Here we define operations for each mode
        ///////////////////////////////////////////////////////////////*/
        
        switch (operation) {
            /* ///////////////////////////////////////////////////////////////
            COLLECT OPERATIONS: Here we collect data from the Live set for conditioning the note genaration
            */
            case operations::collect: {
                
                lock lock {m_mutex};
                
                // midi::Bar* bar{nullptr};
                midi::Event* event{nullptr};
                
                 if (args[0]=="clearTrack" && (track)){
                    track->clear_bars();
                } else  if (args[0]=="barLength" && args.size() >= 2){
                    barLength = args[1];
                    cout << "Bar length: " << barLength << " quarter notes " << c74::min::endl;
                } else if (args[0]=="nBars" && args.size() >= 2){
                    nBars = int(args[1]);
                    if ( (track) && ( nBars <= track->bars_size() )) {
                        cout << "chosen track: " << trackNr << " has " << track->bars_size() << " bars - filling " << nBars << " first bars." << c74::min::endl;
                    } else if ( (track) && ( nBars > track->bars_size() ) ) {
                        int nAddedBars = nBars - track->bars_size();
                        cout << "not enough bars on track #" << trackNr << " add " << nAddedBars <<  " bars" << c74::min::endl;
                        for (int i=0; i<nAddedBars; i++) piece.mutable_tracks(trackNr)->add_bars()->set_beat_length(barLength);
                        
                    } else if ( !(track)) {
                        cerr << "no existing track has been chosen, please choose a track!" << c74::min::endl;
                    }else {
                        cerr << "no existing track has been chosen, unknown BUG!" << c74::min::endl;
                    }
                } else if (args[0]=="notes" && args.size() >= 2){
                    cout << "number of notes: " << args[1] << c74::min::endl;
                    cout << "number of stored events: " << piece.events_size() << c74::min::endl;
                } else if (args[0]=="note" && args.size() >= 5){
                    int startTime = int(float(args[2])*resolution);
                    int endTime = int( ( float(args[2])+float(args[3]) ) * resolution );
                    int pitch = args[1];
                    int velocity = args[4];
                    cout << "pitch: " << pitch << c74::min::endl;
                    cout << "starttime: " << startTime << c74::min::endl;
                    cout << "endtime: " << endTime << c74::min::endl;
                    cout << "velocity: " << velocity << c74::min::endl;
                   
                    // Note On:
                    event = piece.add_events();
                    event->set_pitch(args[1]);
                    event->set_time(startTime*resolution);
                    event->set_velocity(args[4]);
                    // put in appropriate bar
                    int eventNr = piece.events_size()-1;
                    int barNr = int(startTime/(barLength*resolution));
                    cout << "adding event #" << eventNr << " to track #" << trackNr << "’s bar #"  << barNr << c74::min::endl;
                    piece.mutable_tracks(trackNr)->mutable_bars(barNr)->add_events(eventNr);
                    
                    // Note Off:
                    event = piece.add_events();
                    event->set_pitch(pitch);
                    event->set_time(endTime);
                    event->set_velocity(0);
                    eventNr++;
                    // put in appropriate bar
                    barNr = int(endTime/(barLength*resolution));
                    cout << "adding event #" << eventNr << " to track #" << trackNr << "’s bar #" << barNr << c74::min::endl;
                    piece.mutable_tracks(trackNr)->mutable_bars(barNr)->add_events(eventNr);
                    
                }
                
                lock.unlock();
                break;
            }
                
            /* ///////////////////////////////////////////////////////////////
            GENERATE OPERATIONS: Here we generate data from previous note collection
            */
            case operations::generate: {
                lock lock {m_mutex};
                
                std::vector<bool> barSet{};
                
                if (args[0]=="trackNr" && args.size() >= 2){
                    trackNr = int(args[1]);
                    if ( trackNr < piece.tracks_size() ) {
                        // already existing track - update part or all of bars
                        cout << "chosen track: " << trackNr << c74::min::endl;
                        track = piece.mutable_tracks(trackNr);
                    } else {
                        // unexisting track - let’s create it first
                        cout << "Creating new track #" << trackNr  << c74::min::endl;
                        track = piece.add_tracks();
                    }
                } else if (args[0]=="bars" && args.size() >= 2){
                    cout << "Generating " << args.size()-1 << "bars in track: " << trackNr << c74::min::endl;
                }
                
                lock.unlock();
                
                // send stuff
                //output.send();
                break;
            }
                
            /* ///////////////////////////////////////////////////////////////
            EXPAND OPERATIONS: Here we generate data based on previous sequences
            */
            case operations::expand: {
                lock lock {m_mutex};
                
                // do stuff
                
                lock.unlock();
                
                // send stuff
                //output.send();
                break;
            }
            case operations::enum_count:
                break;
        }
        
        
        /*
        ///////////////////////////////////////////////////////////////
        GENERAL OPERATIONS: Here we define operations for all modes
        ///////////////////////////////////////////////////////////////
        */
        {
            /* ///////////////////////////////////////////////////////////////
            TRACK OPERATIONS: mechanism to manage changes in Ableton tracks
                              e.g. moving, ading or deleting tracks in Live
            */
            if (args[0]=="trackNr" && args.size() >= 2){
                trackNr = int(args[1]);
                
                if ( trackNr < piece.tracks_size() ) {
                    cout << "chosen track: " << trackNr << c74::min::endl;
                    track = piece.mutable_tracks(trackNr);
                } else {
                    cout << "the track #" << trackNr << " doesn’t exist! - creating tracks " << piece.tracks_size() << " to "  << trackNr << c74::min::endl;
                    for (int i=piece.tracks_size(); i<=trackNr; i++){
                        piece.add_tracks();
                        cout << "creating track #" << i << c74::min::endl;
                    }
                    track = piece.mutable_tracks(trackNr);
                }
            } else if (args[0]=="tracks_changed" && args.size() >= 1){
                nrTracksMoved=0;
                //pieceCopy.Clear();
                //pieceCopy.set_resolution(resolution);
                //pieceCopy.set_tempo(tempo);
                // copy  events and all other stuff
                cout << "Changing tracks " << nrTracksMoved << c74::min::endl;
            } else if (args[0]=="new_track" && args.size() >= 2){
                int newTrackNr = args[1];
                nrTracksMoved++;
                cout << "Creating new track #" << newTrackNr << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
                //pieceCopy.add_tracks();
            } else if (args[0]=="reorder_track" && args.size() >= 3){
                int trackNr = args[1];
                nrTracksMoved++;
                cout << "Moving existing track #" << trackNr << " to track #" << args[2] << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
                // move track to piece copy
                //pieceCopy.add_tracks()->CopyFrom(piece.tracks()[trackNr]);
            } else if (args[0]=="tracks_done" && args.size() >= 2){
                cout << "Tracks updating, swapping pieces with " << nrTracksMoved << " tracks" << c74::min::endl;
                //piece.Clear();
                //piece.Swap(&pieceCopy);
            }
        }
        {
            /* ///////////////////////////////////////////////////////////////
            OTHER OPERATIONS:
            */
            if (args[0]=="clearNotes"){
                piece.clear_events();
            } else if (args[0]=="clearStatus"){
                status.Clear();
            } else if (args[0]=="tempo" && args.size() >= 2){
                tempo = args[1];
                piece.set_tempo(tempo);
            } else if (args[0]=="get_instruments"){
                output.send( "get_instruments_start" );
                for (const auto& [key, value] : GM) {
                    output.send( "get_instruments", key );
                }
                output.send( "get_instruments_done" );
            } else if (args[0]=="tracks_per_step" && args.size() >= 2){
                param.set_tracks_per_step(args[1]);
            }else if (args[0]=="bars_per_step" && args.size() >= 2){
                param.set_bars_per_step(args[1]);
            } else if (args[0]=="model_dim" && args.size() >= 2){
                param.set_model_dim(args[1]);
            } else if (args[0]=="shuffle" && args.size() >= 2){
                param.set_shuffle(args[1]);
            } else if (args[0]=="percentage" && args.size() >= 2){
                param.set_percentage(args[1]);
            } else if (args[0]=="temperature" && args.size() >= 2){
                param.set_temperature(args[1]);
            } else if (args[0]=="batch_size" && args.size() >= 2){
                param.set_batch_size(args[1]);
            }
        }
        
        
        return {};
    };

    /*//////////////////////////////////////////////////////////////////////
    MAX INPUT MANAGEMENT : Here we define behaviours for Max external’s input
    //////////////////////////////////////////////////////////////////////*/
    
    message<threadsafe::yes> list { this, "list", "Operate on the list. Either add it to the collection or calculate the mean.", process };
    
    message<threadsafe::yes> anything { this, "anything", "Add content to the collection. Only applicable if using the 'collect' operation.", process };
    message<threadsafe::yes> number { this, "number", "Add content to the collection. Only applicable if using the 'collect' operation.", process };

    message<threadsafe::yes> bang { this, "bang", "Send out the collected list. Only applicable if using the 'collect' operation.",
        MIN_FUNCTION {
            lock  lock {m_mutex};
            
            // do stuff
            
            lock.unlock();

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
            cout << "MMM compose object by Metacreation lab - SFU" << c74::min::endl;
            piece.set_resolution(resolution);
            piece.set_tempo(tempo);
            param.set_tracks_per_step(1);
            param.set_bars_per_step(2);
            param.set_model_dim(4);
            param.set_shuffle(false);
            param.set_percentage(100);
            param.set_temperature(1.);
            param.set_batch_size(1);
            param.set_verbose(true);
            param.set_encoder("TRACK_NOTE_DURATION_CONT_ENCODER");
            param.set_ckpt(ckpt_path);
            return {};
        }
    };

/*////////////////////////////////////////////////////////////////////////
PRIVATE MEMBERS : Here we define private members for this class
////////////////////////////////////////////////////////////////////////*/
private:
    atoms m_data; // should go away once all cleaned from Max example
    mutex m_mutex;

    midi::Piece piece, pieceCopy;
    midi::Status status;
    midi::SampleParam param;
            
    int32_t resolution{12};
    int32_t tempo{120};
            
    midi::Track* track{nullptr};
    int trackNr{0};
    int nBars{0};
    float barLength{0};
            
    int nrTracksMoved{0}; // for operations related to track changes

    
    // We need a scene struct for interaction with Live:
    struct LiveScene{
        //std::vector<MMMbar*> bars{};
        int barOffset{0};
        int eventOffset{0};
    };
               
};

MIN_EXTERNAL(MMM_compose);
