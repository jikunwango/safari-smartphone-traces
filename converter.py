import math
import address_helper as ah


def convert_to_rowclone_trace(file_path: str, limit: int, alternant: bool):
    row_bits = ah.g_assemble_levels_bits[4]
    subarray_mask_bits = ah.g_assemble_levels_bits[4] + int(
        math.log2(ah.g_subarray_size)
    )
    tx_offset = ah.g_tx_offset
    row_requests = []
    traces = []
    row_clone_count = 0
    trace_line_count = 0
    with open(file_path, "r") as file:
        while file.readable():
            load_cmd = file.readline()
            store_cmd = file.readline()
            if load_cmd == "" or store_cmd == "":
                break
            if trace_line_count >= limit:
                break
            # ignore high bits
            rd_addr = ah.mask_address(int(load_cmd.split()[1]))
            wr_addr = ah.mask_address(int(store_cmd.split()[2]))
            trace_line_count += 2
            row_requests.append("<read>  " + str(ah.address_to_byte_level(rd_addr)))
            row_requests.append("<write> " + str(ah.address_to_byte_level(wr_addr)))
            # check if read and write are in the same subarray
            if rd_addr >> subarray_mask_bits == wr_addr >> subarray_mask_bits:
                # replace with a rowclone command
                traces.append("0 {} {}".format(rd_addr, wr_addr))
                row_clone_count += 1
            else:
                # split row request into 64 consecutive cache line request
                # here we have two cases, split read/write row into
                # 1>>  consecutive cache line reads then consecutive cache line writes
                # 2>>  alternant read and write in cacheline-grain
                if alternant:
                    for cl in range(64):
                        rd_cl = (rd_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 {}".format(rd_cl))
                        wr_cl = (wr_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 -1 {}".format(wr_cl))
                else:
                    for cl in range(64):
                        rd_cl = (rd_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 {}".format(rd_cl))
                    for cl in range(64):
                        wr_cl = (wr_addr & ~((1 << row_bits) - 1)) + (cl << tx_offset)
                        traces.append("0 -1 {}".format(wr_cl))

    return row_clone_count, trace_line_count, traces, row_requests


trace_count = [
    # 100,
    # 500,
    # 1000,
    # 5000,
    10000,
    # 50000,
    # 100000,
    # 500000,
    # 1000000,
    # 1500000,
]
alternant = True
for case in range(1, 3):
    trace_file = "inputs/case{}.trace".format(case)
    output_dir = "output/convert/case{}/".format(case)
    for limit in trace_count:
        # 1.convert row request to cache line request
        row_clone_count, total_request, traces, row_requests = (
            convert_to_rowclone_trace(trace_file, limit, alternant)
        )
        print(
            "row clone request is {}, total request is {}".format(
                row_clone_count, total_request
            )
        )
        # # 2. save row request to file
        ah.save_to_file(
            row_requests, output_dir + "case{}_row_to_bytes_raw_data.txt".format(case)
        )
        # # 3. convert cache line trace to block level
        ah.traces_array_to_block(traces, output_dir + "case{}_cache_block_raw_data.txt".format(case))
        # # 4. save the final trace
        output_file = (
            "case{}_alternant_mode.trace"
            if alternant
            else "case{}_consecutive_mode.trace"
        )
        ah.save_to_file(traces, output_dir + output_file.format(case))
