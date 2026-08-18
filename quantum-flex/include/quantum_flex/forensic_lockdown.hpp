#ifndef QUANTUM_FLEX_FORENSIC_LOCKDOWN_HPP
#define QUANTUM_FLEX_FORENSIC_LOCKDOWN_HPP

#include <map>
#include <string>

namespace quantum_flex::security {

    struct CommandResult {
        bool success;
        int exit_code;
        std::string output;
    };

    class ICommandExecutor {
    public:
        ICommandExecutor() = default;
        virtual ~ICommandExecutor() = default;
        
        ICommandExecutor(const ICommandExecutor&) = default;
        auto operator=(const ICommandExecutor&) -> ICommandExecutor& = default;
        ICommandExecutor(ICommandExecutor&&) = default;
        auto operator=(ICommandExecutor&&) -> ICommandExecutor& = default;

        // NOLINTNEXTLINE(modernize-use-nodiscard)
        virtual auto execute(const std::string& command) -> CommandResult = 0;
    };

    class SystemCommandExecutor : public ICommandExecutor {
    public:
        // NOLINTNEXTLINE(modernize-use-nodiscard)
        auto execute(const std::string& command) -> CommandResult override;
    };

    class DryRunCommandExecutor : public ICommandExecutor {
    public:
        // NOLINTNEXTLINE(modernize-use-nodiscard)
        auto execute(const std::string& command) -> CommandResult override;
    };

    struct LockdownPolicy {
        bool disable_network = true;
        bool remount_readonly = true;
        bool stop_containers = true;
        bool flush_tpm = true;
        bool isolate_console = true;
        bool reboot_after_lockdown = false;
        bool dry_run = false;
    };

    class ForensicLockdown {
    public:
        ForensicLockdown(ICommandExecutor* executor, const LockdownPolicy& policy);

        // Executes the lockdown sequence and returns a map of action -> success
        // NOLINTNEXTLINE(modernize-use-nodiscard)
        auto execute() -> std::map<std::string, bool>;

    private:
        ICommandExecutor* executor_;
        LockdownPolicy policy_;
        
        auto execute_command(const std::string& cmd, const std::string& action_name) -> bool;
    };

} // namespace quantum_flex::security

#endif // QUANTUM_FLEX_FORENSIC_LOCKDOWN_HPP
