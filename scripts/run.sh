python run.py --path_to_vm docker --headless --observation_type som --model gpt-4-vision-preview --result_dir ./results --test_all_meta_path evaluation_examples/debug.json



python run.py --path_to_vm docker_server --headless --observation_type screenshot --model gpt-4-vision-preview --result_dir ./results --test_all_meta_path evaluation_examples/debug.json



python run_uitars.py --path_to_vm docker_server --headless --observation_type screenshot --model ui-tars --result_dir ./results --test_all_meta_path evaluation_examples/debug.json


python run_uitars.py --path_to_vm docker_server --headless --observation_type screenshot --model ui-tars --result_dir ./results --test_all_meta_path evaluation_examples/test_small.json

ssh -N -L \*:50002:dgx-hyperplane16:8000 zhangbofei@10.2.32.204