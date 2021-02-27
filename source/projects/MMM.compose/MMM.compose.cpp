/// @file
///	@ingroup 	minexamples
///	@copyright	Copyright 2018 The Min-DevKit Authors. All rights reserved.
///	@license	Use of this source code is governed by the MIT License found in the License.md file.

#include "c74_min.h"
#include <vector>
#include <string>
#include <map>
#include <tuple>

#include "./MMM_OPZ/mmm_opz/src/mmm_opz/midi_io.h" // only needed for MIDI input/output
#include "./MMM_OPZ/mmm_opz/src/mmm_opz/protobuf/midi.pb.h"
#include "./MMM_OPZ/mmm_opz/src/mmm_opz/protobuf/midi.pb.cc"
#include "./MMM_OPZ/mmm_opz/src/mmm_opz/sample_internal.h"

std::string ckpt_path = "/Users/bltzr/Documents/Max 8/Packages/MMM/source/projects/MMM.compose/MMM_OPZ/OPZ_MODELS/opz_quant.pt";

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
        description {"Choose the operation to perform with the input. Collect items into a list or calculate the mean from a list."}
    };


    // Here we demonstrate sharing a function to process lists from either the 'list' or 'anything' messages.

    c74::min::function process = MIN_FUNCTION {
        switch (operation) {
            case operations::collect: {
                
                lock lock {m_mutex};
                int trackNr{0};
                int nBars{0};
                MMMtrack* track{};
                
                if (args[0]=="trackNr" && args.size() >= 2){
                    trackNr = int(args[1]);
                    if ( trackNr <= tracks.size() ) {
                        cout << "chosen track: " << trackNr << c74::min::endl;
                        track = &tracks[trackNr];
                    } else {
                        cerr << "the track #" << trackNr << " doesn’t exist!" << c74::min::endl;
                    }
                }
                else if (args[0]=="nBars" && args.size() >= 2){
                    nBars = int(args[1]);
                    if ( (track) && ( nBars <= track->bars.size() ) ) {
                        cout << "chosen track: " << trackNr << " has " << track->bars.size() << " - filling " << nBars << " firsdt bars." << c74::min::endl;
                    } else if ( (track) && ( nBars > track->bars.size() ) ) {
                        cerr << "not enough bars on track #" << trackNr << " - add bars ?" << c74::min::endl;
                    } else {
                        cerr << "no existing track has been chosen, please choose a track!" << c74::min::endl;
                    }
                }
                else if (args[0]=="notes" && args.size() >= 2){
                    eventList.reserve(eventList.size()+int(args[1])*2);
                    cout << "number of notes: " << args[1] << c74::min::endl;
                    cout << "number of stored events: " << eventList.size() << c74::min::endl;
                }
                else if (args[0]=="note" && args.size() >= 5){
                    cout << "pitch: " << args[1] << c74::min::endl;
                    cout << "time: " << int(float(args[2])*12) << c74::min::endl;
                    cout << "endtime: " << int( ( float(args[2])+float(args[3]) ) * 12 ) << c74::min::endl;
                    cout << "velocity: " << args[4] << c74::min::endl;
                   
                    // Note On:
                    eventList.emplace_back(
                        MMMevent{
                            int(float(args[2])*12),
                            args[1],
                            args[4]
                    });
                    
                    // Note Off:
                    eventList.emplace_back(
                        MMMevent{
                            int(float(args[2])*12),
                            int( ( float(args[2])+float(args[3]) ) * 12 ),
                            0
                    });
                }
                
                // update Midi Piece :
                //midi::Track *Mtrack = piece->add_tracks();
                //midi::Bar *Mbar = Mtrack->add_bars();
                
                lock.unlock();
                break;
            }
            case operations::generate: {
                lock lock {m_mutex};
                // do stuff
                lock.unlock();
                // send stuff
                output.send();
                break;
            }
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
        return {};
    };

    message<threadsafe::yes> list { this, "list", "Operate on the list. Either add it to the collection or calculate the mean.", process };
    message<threadsafe::yes> anything { this, "anything", "Add content to the collection. Only applicable if using the 'collect' operation.", process };
    message<threadsafe::yes> number { this, "number", "Add content to the collection. Only applicable if using the 'collect' operation.", process };

    message<threadsafe::yes> bang { this, "bang", "Send out the collected list. Only applicable if using the 'collect' operation.",
        MIN_FUNCTION {
            lock  lock {m_mutex};
            atoms data_copy = m_data;

            m_data.clear();
            lock.unlock();

            output.send(data_copy);
            return {};
        }
    };

    // post to max window == but only when the class is loaded the first time
    message<> maxclass_setup { this, "maxclass_setup",
        MIN_FUNCTION {
            cout << "MMM compose object by Metacreation lab - SFU" << c74::min::endl;
            return {};
        }
    };

private:
    atoms m_data; // should go away once all cleaned from Max example
    mutex m_mutex;
    midi::Piece *piece;
            
    //Creating elements to mimic MMM’s structure:
    struct MMMevent {
        int time{0};
        int pitch{0};
        int velocity{0};
    };
    
    struct MMMbar {
        std::vector<MMMevent*> events{};
        float beatLength{4};
    };
    
    struct MMMtrack {
        std::vector<MMMbar> bars{};
        bool isDrum{0};
        int instrument{0}; // range [0,128)
        TRACK_TYPE type{STANDARD_TRACK};
    };
    
    // Not making a Piece struct for now - here are the Piece’s members:
    std::vector<MMMtrack> tracks{};
    std::vector<MMMevent> eventList{};
    int32_t resolution{12};
    
    // We need a scene struct for interaction with Live:
    struct LiveScene{
        std::vector<MMMbar*> bars{};
        int barOffset{0};
        int eventOffset{0};
    };
               
};

MIN_EXTERNAL(MMM_compose);
