from glob import glob
import json, os

JSON_DIR="../RPI4_32/"

failure = {}
for myfile in glob("%s/20_*.json" % JSON_DIR):
    print(myfile)
    with open(myfile, "r") as jsonfile:
        data = json.load(jsonfile)
    for node in data:
        user_conf = []
        system_conf = []
        user_script = []
        for name in data[node]:
            for info in data[node][name]:
                if "user_conf" in info["states"] and info["ping"]:
                    user_conf.append(info["states"]["user_conf"])
                if "system_conf" in info["states"] and info["ping"]:
                    system_conf.append(info["states"]["system_conf"])
                if "user_script" in info["states"] and info["ping"]:
                    user_script.append(info["states"]["user_script"])
                if not info["ping"]:
                    last_state = list(info["states"].keys())[-1]
                    if last_state not in failure:
                        failure[last_state] = 1
                    else:
                        failure[last_state]+= 1
                    #print("%s: %d" % (last_state, info["states"][last_state]))
print("user_conf")
print(sorted(user_conf))
print(sum(user_conf) / len(user_conf))
print("system_conf")
print(sorted(system_conf))
print(sum(system_conf) / len(system_conf))
print("user_script")
print(sorted(user_script))
print(sum(user_script) / len(user_script))
#print(json.dumps(failure, indent=4))

