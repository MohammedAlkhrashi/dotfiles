#! /bin/bash

file_content=$(cat $1)
file_path=~/${2}
target_file_content=$(tr '\n' ' ' < "$file_path")

temp_file=$(mktemp)

echo "$target_file_content" > "$temp_file"

values=()
value=""

while IFS= read -r line || [[ -n "$line" ]]; do

    if [[ "$line" == *#* ]]; then
        if [[ ! -z "$value" ]]; then
            values+=("$value")
            value=""
        fi

    else
        value="$value$line"
    fi

done < "$1"

if [[ ! -z "$value" ]]; then
    values+=("$value")
fi

for value in "${values[@]}"; do
    if grep -qF "$value" $temp_file; then
        echo "${value}" exists in the configuration file. Skipping writing it
    else
        echo "$value" >> $file_path
    fi
done

rm "$temp_file"
