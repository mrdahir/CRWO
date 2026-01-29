// ========================================
// INVENTORY EDITING ENHANCEMENTS
// Adds edit and delete functionality to restock inventory page
// ========================================

// Override displayProducts function to add edit/delete buttons
(function () {
    'use strict';

    // Store original function if it exists
    const originalDisplayProducts = window.displayProducts;

    window.displayProducts = function (products) {
        const container = document.getElementById('productResults');

        if (!products || products.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-5">No products found</div>';
            return;
        }

        const isSuperuser = {{ request.user.is_superuser| yesno: "true,false"
    }
};

container.innerHTML = products.map(product => `
        <div class="card mb-2">
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <div class="fw-bold">${product.name}</div>
                        <div class="text-muted small">${product.brand} • ${product.category}</div>
                        <div class="mt-1">
                            <span class="badge ${product.current_stock <= product.low_stock_threshold ? 'bg-danger' : 'bg-success'}">
                                Stock: ${product.current_stock}
                            </span>
                            ${product.current_stock <= product.low_stock_threshold ?
        `<span class="badge bg-warning ms-1">Low Stock</span>` : ''}
                        </div>
                        <div class="text-muted small mt-1">
                            USD: $${product.selling_price_usd} | SOS: ${product.selling_price_sos} | ETB: ${product.selling_price_etb}
                        </div>
                    </div>
                    <div class="d-flex flex-column gap-1">
                        <button type="button" class="btn btn-sm btn-primary" 
                                onclick="openRestockModal(${product.id}, '${product.name.replace(/'/g, "\\'")}', ${product.current_stock})">
                            <i class="fas fa-plus"></i> Restock
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-secondary" 
                                onclick="openEditModal(${product.id}, '${product.name.replace(/'/g, "\\'")}', ${product.purchase_price}, ${product.selling_price_usd}, ${product.selling_price_sos}, ${product.selling_price_etb})">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        ${isSuperuser ? `
                        <button type="button" class="btn btn-sm btn-outline-danger" 
                                onclick="confirmDelete(${product.id}, '${product.name.replace(/'/g, "\\'")}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>
        `).join('');
    };

// Edit Product Functions
window.openEditModal = function (productId, productName, purchasePrice, priceUSD, priceSOS, priceETB) {
    document.getElementById('editProductId').value = productId;
    document.getElementById('editProductName').value = productName;
    document.getElementById('editPurchasePrice').value = purchasePrice;
    document.getElementById('editPriceUSD').value = priceUSD;
    document.getElementById('editPriceSOS').value = priceSOS;
    document.getElementById('editPriceETB').value = priceETB;

    const modal = new bootstrap.Modal(document.getElementById('editProductModal'));
    modal.show();
};

window.submitEdit = function () {
    const productId = document.getElementById('editProductId').value;
    const formData = new FormData(document.getElementById('editProductForm'));

    const submitBtn = document.querySelector('#editProductModal .btn-primary');
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';
    submitBtn.disabled = true;

    fetch(`/api/product/${productId}/update/`, {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (window.showToast) {
                    showToast(data.message, 'success');
                } else {
                    alert(data.message);
                }
                bootstrap.Modal.getInstance(document.getElementById('editProductModal')).hide();
                if (window.loadAllProducts) loadAllProducts();
            } else {
                if (window.showToast) {
                    showToast(data.error || 'Failed to update product', 'error');
                } else {
                    alert(data.error || 'Failed to update product');
                }
            }
        })
        .catch(error => {
            console.error('Error updating product:', error);
            if (window.showToast) {
                showToast('Error updating product', 'error');
            } else {
                alert('Error updating product');
            }
        })
        .finally(() => {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        });
};

// Delete Product Functions
window.confirmDelete = function (productId, productName) {
    document.getElementById('deleteProductId').value = productId;
    document.getElementById('deleteProductName').textContent = productName;

    const modal = new bootstrap.Modal(document.getElementById('deleteProductModal'));
    modal.show();
};

window.submitDelete = function () {
    const productId = document.getElementById('deleteProductId').value;

    const submitBtn = document.querySelector('#deleteProductModal .btn-danger');
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
    submitBtn.disabled = true;

    fetch(`/api/product/${productId}/delete/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json'
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (window.showToast) {
                    showToast(data.message, 'success');
                } else {
                    alert(data.message);
                }
                bootstrap.Modal.getInstance(document.getElementById('deleteProductModal')).hide();
                if (window.loadAllProducts) loadAllProducts();
            } else {
                if (window.showToast) {
                    showToast(data.error || 'Failed to delete product', 'error');
                } else {
                    alert(data.error || 'Failed to delete product');
                }
            }
        })
        .catch(error => {
            console.error('Error deleting product:', error);
            if (window.showToast) {
                showToast('Error deleting product', 'error');
            } else {
                alert('Error deleting product');
            }
        })
        .finally(() => {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        });
};
}) ();
