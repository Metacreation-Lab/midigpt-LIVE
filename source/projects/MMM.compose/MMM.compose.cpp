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
    
    struct MMMevent {
        int time{0};
        int pitch{0};
        int velocity{0};
    };
    
    std::vector<MMMevent> eventList{};
    
    // For enum attributes you first define your enum class.
    // The indices must start at zero and increase sequentially.

    enum class operations : int { collect, average, product, enum_count };

    // You then define the symbols to associate with your enum values.
    // These will be indexed starting at zero.
    // You must have one for each item in the actual enum.

    enum_map operations_range = {"collect", "average", "product"};

    // Finally, you create the attribute...
    // specialized with the type of the enum and with the range passed as one of the optional args.

    attribute<operations> operation { this, "operation", operations::collect, operations_range,
        description {"Choose the operation to perform with the input. Collect items into a list or calculate the mean from a list."}
    };


    // Here we demonstrate sharing a function to process lists from either the 'list' or 'anything' messages.

    c74::min::function process = MIN_FUNCTION {
        switch (operation) {
            case operations::collect: {
                lock lock {m_mutex};
                if (args[0]=="notes" && args.size() >= 2){
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
                break;
            }
            case operations::average: {
                lock lock {m_mutex};
                auto x = from_atoms<std::vector<double>>(args);
                auto y = math::mean<double>(x);
                lock.unlock();
                output.send(y.first, y.second);
                break;
            }
            case operations::product: {
                lock lock {m_mutex};
                auto x = from_atoms<std::vector<double>>(args);
                auto y = std::accumulate(std::begin(x), std::end(x), 1.0, std::multiplies<double>());
                lock.unlock();
                output.send(y);
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
    atoms m_data;
    mutex m_mutex;
};

MIN_EXTERNAL(MMM_compose);
