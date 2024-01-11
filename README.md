## AWS Resource Management and Right-Sizing Tool

### Overview

This Python script is a versatile tool for managing and optimizing AWS resources based on your specified configurations. It provides automated cleanup and right-sizing of AWS resources, ensuring cost-efficiency and resource optimization in your AWS environment.

### Features

- **Resource Cleanup:** Easily identify and clean up unattached EBS volumes, unused ECR repositories, old EBS snapshots, and idle NAT Gateways.

- **Right-Sizing:** Automatically identify and resize EC2 instances that are underutilized, based on CPU and memory thresholds defined in your configuration.

- **Configuration-Driven:** All settings are controlled through a user-friendly `config.json` file, allowing you to tailor the tool to your specific AWS environment.

- **Label-Based Policies:** Define policies for resource management and right-sizing based on instance labels, providing granular control over different resource types.

- **Flexible Skipping:** Specify resource types to skip right-sizing based on labels, preventing unwanted changes to specific resources.

### Getting Started

1. Clone this repository to your local machine.
2. Configure your AWS credentials and customize settings in the `config.json` file.
3. Run the script with the desired environment to initiate resource cleanup and right-sizing.

### Usage Example

```shell
python aws_resource_manager.py ort2
```

Replace `ort2` with the environment name defined in your `config.json` file.

### Contributing

Contributions are welcome! If you have suggestions or improvements, please feel free to open an issue or submit a pull request.

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Feel free to customize this description to fit your repository's specific details and style.
