def hex_format(value: int):
    hex_str = f"{value:016x}"
    formatted_hex = " ".join(hex_str[i : i + 4] for i in range(0, len(hex_str), 4))
    return formatted_hex


def convert_traces_as_hex(file_path: str):
    with open(file_path, "r") as file:
        for line in file:
            print(hex_format(int(line)))


convert_traces_as_hex("address.txt")
