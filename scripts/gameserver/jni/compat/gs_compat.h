// gcc 4.9 / gnustl compatibility shims for the GameServer build
//
// This header is FORCE-INCLUDED (-include) into every C++ TU via
// COMMON_FLAGS. g3log also compiles C sources (execinfo_android.c) with the
// same flags — in C mode the C++ standard headers below are fatal (gcc 4.9
// headers #error without -std=c++11), so everything here is guarded by
// __cplusplus and the C TUs get a no-op include.
#pragma once

#ifdef __cplusplus

#include <type_traits>
#include <memory>
#include <cstddef>
#include <unordered_set>
#include <unordered_map>
#include <functional>
#include <string>
#include <vector>
#include <algorithm>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>

namespace std {
template <class T> using make_unsigned_t = typename make_unsigned<T>::type;
template <class T> using make_signed_t   = typename make_signed<T>::type;
template <class T> using remove_const_t  = typename remove_const<T>::type;
template <class T> using remove_volatile_t = typename remove_volatile<T>::type;
template <class T> using remove_cv_t     = typename remove_cv<T>::type;
template <class T> using add_const_t     = typename add_const<T>::type;
template <class T> using remove_pointer_t = typename remove_pointer<T>::type;
template <class T> using remove_reference_t = typename remove_reference<T>::type;
template <bool B, class T = void> using enable_if_t = typename enable_if<B, T>::type;
template <bool B, class T, class F> using conditional_t = typename conditional<B, T, F>::type;
template <class T> using decay_t = typename decay<T>::type;
template <class... Ts> using common_type_t = typename common_type<Ts...>::type;
template <class T> using underlying_type_t = typename underlying_type<T>::type;
template <class T> using result_of_t = typename result_of<T>::type;

// C++14 make_unique (gcc 4.9 lacks it)
template <class T> struct _GsUniqueIf { template <class... A> static unique_ptr<T> _make(A&&... a) { return unique_ptr<T>(new T(std::forward<A>(a)...)); } };
template <class T> struct _GsUniqueIf<T[]> { template <class A> static unique_ptr<T[]> _make(A&& a) { return unique_ptr<T[]>(new typename remove_extent<T>::type[a]()); } };
template <class T, class... Args> unique_ptr<T> make_unique(Args&&... args) { return _GsUniqueIf<T>::_make(std::forward<Args>(args)...); }
}
// gnustl for android lacks std::to_string
#include <cstdio>
#include <cstdlib>
namespace std {
namespace detail {
template <class T> inline string _gs_to_string(const char* fmt, T v) {
    char buf[64]; snprintf(buf, sizeof(buf), fmt, v); return string(buf);
}
}
inline string to_string(int v)                { return detail::_gs_to_string("%d", v); }
inline string to_string(unsigned v)           { return detail::_gs_to_string("%u", v); }
inline string to_string(long v)               { return detail::_gs_to_string("%ld", v); }
inline string to_string(unsigned long v)      { return detail::_gs_to_string("%lu", v); }
inline string to_string(long long v)          { return detail::_gs_to_string("%lld", v); }
inline string to_string(unsigned long long v) { return detail::_gs_to_string("%llu", v); }
inline string to_string(float v)              { return detail::_gs_to_string("%f", v); }
inline string to_string(double v)             { return detail::_gs_to_string("%f", v); }
inline string to_string(long double v)        { return detail::_gs_to_string("%Lf", v); }
}
// gnustl for android lacks std::sto*
#include <stdexcept>
namespace std {
inline int stoi(const string& s, size_t* pos = nullptr, int base = 10) {
    if (s.empty()) throw invalid_argument("stoi"); const char* c = s.c_str(); char* e = nullptr;
    long r = strtol(c, &e, base); if (e == c) throw invalid_argument("stoi"); if (pos) *pos = (size_t)(e - c); return (int)r;
}
inline long stol(const string& s, size_t* pos = nullptr, int base = 10) {
    const char* c = s.c_str(); char* e = nullptr; long r = strtol(c, &e, base); if (e == c) throw invalid_argument("stol"); if (pos) *pos = (size_t)(e - c); return r;
}
inline unsigned long stoul(const string& s, size_t* pos = nullptr, int base = 10) {
    const char* c = s.c_str(); char* e = nullptr; unsigned long r = strtoul(c, &e, base); if (e == c) throw invalid_argument("stoul"); if (pos) *pos = (size_t)(e - c); return r;
}
inline long long stoll(const string& s, size_t* pos = nullptr, int base = 10) {
    const char* c = s.c_str(); char* e = nullptr; long long r = strtoll(c, &e, base); if (e == c) throw invalid_argument("stoll"); if (pos) *pos = (size_t)(e - c); return r;
}
inline unsigned long long stoull(const string& s, size_t* pos = nullptr, int base = 10) {
    const char* c = s.c_str(); char* e = nullptr; unsigned long long r = strtoull(c, &e, base); if (e == c) throw invalid_argument("stoull"); if (pos) *pos = (size_t)(e - c); return r;
}
inline float stof(const string& s, size_t* pos = nullptr) {
    const char* c = s.c_str(); char* e = nullptr; float r = strtof(c, &e); if (e == c) throw invalid_argument("stof"); if (pos) *pos = (size_t)(e - c); return r;
}
inline double stod(const string& s, size_t* pos = nullptr) {
    const char* c = s.c_str(); char* e = nullptr; double r = strtod(c, &e); if (e == c) throw invalid_argument("stod"); if (pos) *pos = (size_t)(e - c); return r;
}
}

#endif /* __cplusplus */
