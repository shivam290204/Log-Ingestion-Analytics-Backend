#include <algorithm>           // std::max
#include <condition_variable>  // thread coordination
#include <cstdlib>             // basic utilities
#include <fstream>             // file read/write
#include <iostream>            // input/output (cout)
#include <mutex>               // thread locking
#include <queue>               // queue data structure
#include <sstream>             // string parsing
#include <string>              // strings
#include <thread>              // multithreading
#include <vector>              // dynamic arrays


struct LogEntry {
    std::string timestamp;
    std::string level;
    std::string service;
    std::string message;
};

class ThreadSafeQueue {
public:
    void push(const LogEntry &entry) {
        std::lock_guard<std::mutex> lock(mutex_);
        queue_.push(entry);
        cv_.notify_one();
    }

    bool pop(LogEntry &out) {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [&] { return finished_ || !queue_.empty(); });
        if (queue_.empty()) {
            return false; // finished and nothing left
        }
        out = queue_.front();
        queue_.pop();
        return true;
    }

    void mark_finished() {
        std::lock_guard<std::mutex> lock(mutex_);
        finished_ = true;
        cv_.notify_all();
    }

private:
    std::queue<LogEntry> queue_;
    std::mutex mutex_;
    std::condition_variable cv_;
    bool finished_ = false;
};

// Shared output writer that serializes writes to stdout or an optional file.
class OutputWriter {
public:
    explicit OutputWriter(const std::string &path) {
        if (!path.empty()) {
            file_.open(path, std::ios::app);
            if (file_.is_open()) {
                target_ = &file_;
            } else {
                std::cerr << "Unable to open output file: " << path << ". Falling back to stdout.\n";
            }
        }
    }

    void write(const LogEntry &entry, int worker_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        (*target_) << "[" << entry.timestamp << "] "
                   << entry.level << ' '
                   << entry.service << ' '
                   << entry.message;
        if (target_ == &std::cout) {
            (*target_) << " (worker " << worker_id << ")";
        }
        (*target_) << '\n';
        target_->flush();
    }

private:
    std::mutex mutex_;
    std::ofstream file_;
    std::ostream *target_ = &std::cout;
};

bool parse_line(const std::string &line, LogEntry &entry) {
    std::istringstream iss(line);
    std::string date, time;
    if (!(iss >> date >> time >> entry.level >> entry.service)) {
        return false;
    }
    std::string rest;
    std::getline(iss, rest);
    if (!rest.empty() && rest[0] == ' ') {
        rest.erase(0, 1);
    }
    entry.timestamp = date + " " + time;
    entry.message = rest;
    return true;
}

void worker_loop(ThreadSafeQueue &queue, OutputWriter &writer, int id) {
    LogEntry entry;
    while (queue.pop(entry)) {
        writer.write(entry, id);
    }
}

int main() {
    const char *file_env = std::getenv("LOG_FILE_PATH");
    const std::string log_file = file_env ? file_env : "/data/logs/logs.txt";
    const char *worker_env = std::getenv("WORKER_COUNT");
    int worker_count = worker_env ? std::max(1, std::atoi(worker_env)) : 4;
    const char *output_env = std::getenv("OUTPUT_FILE_PATH");
    const std::string output_path = output_env ? output_env : "";

    ThreadSafeQueue queue;
    OutputWriter writer(output_path);
    std::vector<std::thread> workers;
    workers.reserve(worker_count);
    for (int i = 0; i < worker_count; ++i) {
        workers.emplace_back(worker_loop, std::ref(queue), std::ref(writer), i);
    }

    std::ifstream infile(log_file);
    if (!infile.is_open()) {
        std::cerr << "Unable to open log file: " << log_file << "\n";
        queue.mark_finished();
        for (auto &t : workers) {
            t.join();
        }
        return 1;
    }

    std::string line;
    while (std::getline(infile, line)) {
        LogEntry entry;
        if (!parse_line(line, entry)) {
            std::cerr << "Skipping malformed line: " << line << "\n";
            continue;
        }
        queue.push(entry);
    }

    queue.mark_finished();
    for (auto &t : workers) {
        t.join();
    }

    std::cout << "Ingestion complete.\n";
    return 0;
}
