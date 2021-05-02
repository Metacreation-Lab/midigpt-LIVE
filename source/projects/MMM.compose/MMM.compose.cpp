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

std::string ckpt_path = "/Users/bltzr/Dropbox/My Mac (Pias-MBP)/Documents/Max 8/Packages/MMM4LIVE/source/projects/MMM.compose";

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
        
        /* ///////////////////////////////////////////////////////////////
        CONTEXTUAL OPERATIONS: Here we define operations for each mode
        ///////////////////////////////////////////////////////////////*/
        
        switch (operation) {
            /* ///////////////////////////////////////////////////////////////
            COLLECT OPERATIONS: Here we collect data from the Live set for conditioning the note genaration
            */
            case operations::collect: {
                
                lock lock {m_mutex};
                int trackNr{0};
                int nBars{0};
                float barLength{0};
                MMMtrack* track{};
                
                if (args[0]=="trackNr" && args.size() >= 2){
                    trackNr = int(args[1]);
                    if ( trackNr < tracks.size() ) {
                        cout << "chosen track: " << trackNr << c74::min::endl;
                        track = &tracks[trackNr];
                    } else {
                        cout << "the track #" << trackNr << " doesn’t exist! - creating tracks " << tracks.size() << " to "  << trackNr << c74::min::endl;
                        for (int i=tracks.size(); i<=trackNr; i++){
                            tracks.emplace_back(MMMtrack());
                            cout << "creating track #" << i << c74::min::endl;
                        }
                        track = &tracks[trackNr];
                    }
                }
                else if (args[0]=="barLength" && args.size() >= 2){
                    barLength = args[1];
                    cout << "Bar length: " << barLength << " quarter notes " << c74::min::endl;
                }
                else if (args[0]=="nBars" && args.size() >= 2){
                    nBars = int(args[1]);
                    if ( (track) && ( nBars <= track->barNr() ) ) {
                        cout << "chosen track: " << trackNr << " has " << track->barNr() << " - filling " << nBars << " firsdt bars." << c74::min::endl;
                    } else if ( (track) && ( nBars > track->barNr() ) ) {
                        cerr << "not enough bars on track #" << trackNr << " - add bars ?" << c74::min::endl;
                    } else if ( !(track)) {
                        cerr << "no existing track has been chosen, please choose a track!" << c74::min::endl;
                    }else {
                        cerr << "no existing track has been chosen, unknown BUG!" << c74::min::endl;
                    }
                }
                else if (args[0]=="notes" && args.size() >= 2){
                    events.reserve(events.size()+int(args[1])*2);
                    cout << "number of notes: " << args[1] << c74::min::endl;
                    cout << "number of stored events: " << events.size() << c74::min::endl;
                }
                else if (args[0]=="note" && args.size() >= 5){
                    cout << "pitch: " << args[1] << c74::min::endl;
                    cout << "time: " << int(float(args[2])*12) << c74::min::endl;
                    cout << "endtime: " << int( ( float(args[2])+float(args[3]) ) * 12 ) << c74::min::endl;
                    cout << "velocity: " << args[4] << c74::min::endl;
                   
                    // Note On:
                    events.emplace_back(
                        MMMevent(
                            int(float(args[2])*12),
                            args[1],
                            args[4]
                    ));
                    
                    // Note Off:
                    events.emplace_back(
                         MMMevent(
                            int(float(args[2])*12),
                            int( ( float(args[2])+float(args[3]) ) * 12 ),
                            0
                    ));
                }
                
                
                // update Midi Piece :
                //midi::Track *Mtrack = piece->add_tracks();
                //midi::Bar *Mbar = Mtrack->add_bars();
                
                lock.unlock();
                break;
            }
            /* ///////////////////////////////////////////////////////////////
            GENERATE OPERATIONS: Here we generate data from previous note collection
            */
            case operations::generate: {
                lock lock {m_mutex};
                
                int trackNr{0};
                std::vector<bool> barSet{};
                MMMtrack* track{};
                
                if (args[0]=="trackNr" && args.size() >= 2){
                    trackNr = int(args[1]);
                    if ( trackNr <= tracks.size() ) {
                        // already existing track - update part or all of bars
                        cout << "chosen track: " << trackNr << c74::min::endl;
                        track = &tracks[trackNr];
                    } else {
                        // unexisting track - let’s create it firs
                        cout << "Creating new track #" << trackNr  << c74::min::endl;
                        track = &tracks.emplace_back(MMMtrack());
                    }
                }
                else if (args[0]=="bars" && args.size() >= 2){
                    cout << "Adding " << args.size()-1 << "bars to track: " << trackNr << c74::min::endl;
                }
                
                lock.unlock();
                // send stuff
                output.send();
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
                output.send();
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
            if (args[0]=="tracks_changed" && args.size() >= 1){
                nrTracksMoved=0;
                //pieceCopy->Clear();
                cout << "Changing tracks " << nrTracksMoved << c74::min::endl;
            }
            else if (args[0]=="new_track" && args.size() >= 2){
                int newTrackNr = args[1];
                nrTracksMoved++;
                cout << "Creating new track #" << newTrackNr << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
                //pieceCopy->add_tracks();
            }
            else if (args[0]=="reorder_track" && args.size() >= 3){
                int trackNr = args[1];
                nrTracksMoved++;
                cout << "Moving existing track #" << trackNr << " to track #" << args[2] << " / " <<  nrTracksMoved  << " in piece copy" << c74::min::endl;
                // move track to piece copy
                //pieceCopy->add_tracks()->CopyFrom(piece->tracks()[trackNr]);
            }
            else if (args[0]=="tracks_done" && args.size() >= 2){
                cout << "Tracks updating, swapping pieces with " << nrTracksMoved << " tracks" << c74::min::endl;
                // piece->Clear();
                // piece->Swap(pieceCopy);
            }
        }
        {
            /* ///////////////////////////////////////////////////////////////
            OTHER OPERATIONS:
            */
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
            piece = new midi::Piece();
            pieceCopy = new midi::Piece();
            return {};
        }
    };

/*////////////////////////////////////////////////////////////////////////
PRIVATE MEMEBERS : Here we define private members for this class
////////////////////////////////////////////////////////////////////////*/
private:
    atoms m_data; // should go away once all cleaned from Max example
    mutex m_mutex;
            
    int nrTracksMoved{0}; // for operations related to track changes
    midi::Piece *piece, *pieceCopy;
            
    //Creating elements to mimic MMM’s structure:
    class MMMevent {
            int m_time{0};
            int m_pitch{0};
            int m_velocity{0};
        public:
            MMMevent(int time, int pitch, int velocity):
                m_time(time),
                m_pitch(pitch),
                m_velocity(velocity)
            {};
            
    };
    
    class MMMbar {
            std::vector<MMMevent*> m_events{};
            float m_beatLength{4};
        public:
            size_t eventNr() {return m_events.size();}
            float barLength(float length) {return m_beatLength = length;};
    };
    
    class MMMtrack {
            std::vector<MMMbar> m_bars{};
            bool m_isDrum{0};
            int m_instrument{0}; // range [0,128)
            TRACK_TYPE m_type{STANDARD_TRACK};
        public:
            MMMtrack() {
                //std::cout << "creating track" << c74::min::endl;
            };
            
            MMMtrack(MMMtrack&& other)
            : m_bars(std::move(other.m_bars)), m_isDrum(std::move(other.m_isDrum)), m_instrument(std::move(other.m_instrument)), m_type(std::move(other.m_type))
            {
                //cout << "moving track" << c74::min::endl;
            };
            size_t barNr() {return m_bars.size();}
    };
    
    // Not making a Piece struct for now - here are the Piece’s members:
    std::vector<MMMtrack> tracks{};
    std::vector<MMMevent> events{};
    int32_t resolution{12};
    
    // We need a scene struct for interaction with Live:
    struct LiveScene{
        std::vector<MMMbar*> bars{};
        int barOffset{0};
        int eventOffset{0};
    };
               
};

MIN_EXTERNAL(MMM_compose);
