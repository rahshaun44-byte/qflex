#include "quantum_flex/forensic_lockdown.hpp"

#include <cstdlib>
#include <iostream>
#include <map>
#include <string>

namespace quantum_flex::security {

    auto SystemCommandExecutor::execute(const std::string& command) -> CommandResult {
        // NOLINTNEXTLINE(concurrency-mt-unsafe,cert-env33-c,bugprone-command-processor)
        const int result = std::system(command.c_str());
        return {
            .success = (result == 0),
            .exit_code = result,
            .output = "" // Not capturing output in basic std::system wrapper
        };
    }

    auto DryRunCommandExecutor::execute(const std::string& command) -> CommandResult {
        std::cout << "[DRY RUN] Would execute: " << command << "\n";
        return {
            .success = true,
            .exit_code = 0,
            .output = "[DRY RUN SUCCESS]"
        };
    }

    ForensicLockdown::ForensicLockdown(ICommandExecutor* executor, const LockdownPolicy& policy)
        : executor_(executor), policy_(policy) {}

    auto ForensicLockdown::execute_command(const std::string& cmd, const std::string& action_name) -> bool {
        if (policy_.dry_run) {
            std::cout << "[DRY RUN] Would " << action_name << "\n";
            return true;
        }

        const CommandResult result = executor_->execute(cmd);
        if (!result.success) {
            std::cerr << "[!] Warning: Lockdown action failed: " << action_name << " (Cmd: " << cmd << ")\n";
        }
        return result.success;
    }

    auto ForensicLockdown::execute() -> std::map<std::string, bool> {
        std::map<std::string, bool> results;

        std::cout << "[!] HARDWARE LOCKDOWN INITIATED\n";

        if (policy_.disable_network) {
            bool network_success = true;
            network_success &= execute_command("ip link set eth0 down", "disable eth0 interface");
            network_success &= execute_command("nft flush ruleset", "flush nftables ruleset");
            network_success &= execute_command("nft add table inet quarantine", "create nftables quarantine table");
            network_success &= execute_command("nft add chain inet quarantine input { type filter hook input priority 0; policy drop; }", "drop input traffic");
            network_success &= execute_command("nft add chain inet quarantine output { type filter hook output priority 0; policy drop; }", "drop output traffic");
            results["network"] = network_success;
        }

        if (policy_.stop_containers) {
            results["containers"] = execute_command("podman rm -fa --time 0", "stop and remove all podman containers");
        }

        if (policy_.remount_readonly) {
            bool fs_success = true;
            fs_success &= execute_command("sync", "sync disks");
            fs_success &= execute_command("mount -o remount,ro /", "remount root filesystem read-only");
            results["filesystem"] = fs_success;
        }

        if (policy_.flush_tpm) {
            bool tpm_success = true;
            tpm_success &= execute_command("tpm2_flushcontext -t", "flush TPM transient handles");
            tpm_success &= execute_command("tpm2_flushcontext -l", "flush TPM loaded handles");
            tpm_success &= execute_command("tpm2_flushcontext -s", "flush TPM saved handles");
            results["TPM"] = tpm_success;
        }

        if (policy_.isolate_console) {
            bool console_success = true;
            console_success &= execute_command("systemctl stop sshd", "stop sshd service");
            console_success &= execute_command("pkill -9 -u root sshd", "kill active ssh sessions");
            results["console"] = console_success;
        }

        if (policy_.reboot_after_lockdown) {
            results["reboot"] = execute_command("reboot -f", "force reboot system");
        }

        std::cout << "[!] LOCKDOWN SEQUENCE COMPLETED.\n";
        return results;
    }

} // namespace quantum_flex::security
