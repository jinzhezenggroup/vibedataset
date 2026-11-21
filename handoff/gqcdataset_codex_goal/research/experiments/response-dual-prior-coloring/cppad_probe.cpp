// Compare requested derivative entries with the structural sparsity supplied to CppAD.
#include <cppad/cppad.hpp>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

using Index = CppAD::vector<size_t>;
using Values = CppAD::vector<double>;
using Pattern = CppAD::sparse_rc<Index>;
using Entries = CppAD::sparse_rcv<Index, Values>;
constexpr size_t dim = 6;

bool sparse_jac_for();  // Upstream executable examples with numerical assertions.
bool sparse_jac_rev();

void compare(bool physically_dense, bool claim_diagonal_support, bool request_cross,
             bool forward, bool comma) {
    CppAD::vector<CppAD::AD<double>> x(dim), y(dim);
    for (size_t j = 0; j < dim; ++j) x[j] = 0.0;
    CppAD::Independent(x);
    for (size_t i = 0; i < dim; ++i) {
        y[i] = 0.0;
        for (size_t j = 0; j < dim; ++j) {
            if (physically_dense || i == j) y[i] += double(1 + i * dim + j) * x[j];
        }
    }
    CppAD::ADFun<double> f(x, y);
    Pattern identity(dim,dim,dim);
    for (size_t i = 0; i < dim; ++i) identity.set(i,i,i);
    Pattern tape_support;
    f.for_jac_sparsity(identity, false, false, true, tape_support);
    const Pattern& pattern = claim_diagonal_support ? identity : tape_support;

    Pattern requests(dim,dim,request_cross ? 2*dim - 1 : dim);
    size_t slot = 0;
    for (size_t i = 0; i < dim; ++i) {
        for (size_t j = 0; j < dim; ++j) {
            bool needed = request_cross ? (i == dim-1 || j == dim-1) : i == j;
            if (needed) requests.set(slot++,i,j);
        }
    }
    Entries subset(requests);
    Values point(dim);
    for (size_t j = 0; j < dim; ++j) point[j] = 0.0;
    CppAD::sparse_jac_work work;
    size_t directions = forward ? f.sparse_jac_for(1, point, subset, pattern, "cppad", work)
                                : f.sparse_jac_rev(point, subset, pattern, "cppad", work);
    double max_error = 0.0;
    for (size_t k = 0; k < subset.nnz(); ++k) {
        double ref = double(1 + subset.row()[k] * dim + subset.col()[k]);
        max_error = std::max(max_error,std::abs(subset.val()[k] - ref));
    }
    bool should_accept = !physically_dense || !claim_diagonal_support;
    if ((max_error == 0.0) != should_accept) {
        std::cerr << "Recovered entry comparison failed\n";
        std::exit(1);
    }
    std::cout << (comma ? ",\n" : "") << "{\"mode\":\"" << (forward ? "fwd":"rev")
              << "\",\"tape_support\":" << tape_support.nnz() << ",\"supplied_support\":" << pattern.nnz()
              << ",\"requested_entries\":" << subset.nnz() << ",\"directions\":" << directions
              << ",\"max_entry_error\":" << max_error << "}";
}

int main() {
    if (!sparse_jac_for() || !sparse_jac_rev()) return 1;
    std::cout << "{\"upstream_forward_and_reverse_examples_passed\":true,\"cases\":[\n";
    bool comma = false;
    for (bool forward : {true, false}) {
        compare(false,false,false,forward,comma);
        compare(true,false,false,forward,true);
        compare(true,true,false,forward,true);
        compare(true,false,true,forward,true);
        comma = true;
    }
    std::cout << "]}\n";
}
