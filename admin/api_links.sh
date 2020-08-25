#!/bin/bash
API_FILES='webapp.py'
for file in $API_FILES; do
    echo "##################### $file"
    route_key=''
    func_key=''
    endpoint=''
    grep -B 3 def blueprints/$file | while read -r line ; do
        if [[ $line == *"route"* ]]; then
            quote=$(echo -e "\x22")
            line=$(echo $line | cut --delimiter=$quote -f2)
            # Count the number of slashes
            if [ $(echo $line | awk -F\/ '{print NF-1}') -eq 1 ]; then
                endpoint='yes'
                # Remove the leading slash
                route_key=$(echo ${line:1})
            else
                endpoint='yes'
                route_key=$(echo $line | cut --delimiter=/ -f3)
            fi
        fi
        if [[ ! -z "$(echo $endpoint)" && $line == "def"* ]]; then
            func_name=$(echo $line | sed 's/def //' | sed 's/(.*)://')
        fi
        if [[ $line == "--"* ]]; then
            if [[ $route_key == $func_name ]]; then
                echo $route_key
            else
                echo $route_key
                echo $func_name
            fi
            endpoint=''
            route_key=''
            func_name=''
            echo '#########################'
        fi
    done
done
