(function () {
    'use strict';

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
        } else {
            callback();
        }
    }

    ready(function () {
        const form = document.querySelector('[data-invoice-form]');
        if (!form) return;

        const customerSelect = form.querySelector('#id_customer');
        const propertySelect = form.querySelector('#id_property');
        const workInputs = Array.from(
            form.querySelectorAll('input[name="work_entries"]')
        );
        const emptyMessage = form.querySelector('[data-work-entry-empty]');

        if (!customerSelect || !propertySelect) return;

        const propertyOptions = Array.from(propertySelect.options).map(function (option) {
            return {
                value: option.value,
                text: option.textContent,
                customerId: option.dataset.customerId || '',
                selected: option.selected,
            };
        });

        function replacePropertyOptions() {
            const customerId = customerSelect.value;
            const previousValue = propertySelect.value;
            const available = propertyOptions.filter(function (option) {
                return option.value && option.customerId === customerId;
            });

            propertySelect.replaceChildren();
            const blank = document.createElement('option');
            blank.value = '';
            if (!customerId) {
                blank.textContent = 'Select a customer first';
            } else if (!available.length) {
                blank.textContent = 'No active properties for this customer';
            } else {
                blank.textContent = 'Select a property (optional)';
            }
            propertySelect.appendChild(blank);

            available.forEach(function (optionData) {
                const option = document.createElement('option');
                option.value = optionData.value;
                option.textContent = optionData.text;
                option.dataset.customerId = optionData.customerId;
                propertySelect.appendChild(option);
            });

            const previousStillAvailable = available.some(function (option) {
                return option.value === previousValue;
            });
            if (previousStillAvailable) {
                propertySelect.value = previousValue;
            } else if (!previousValue) {
                const initiallySelected = available.find(function (option) {
                    return option.selected;
                });
                propertySelect.value = initiallySelected ? initiallySelected.value : '';
            }
            propertySelect.disabled = !customerId || !available.length;
        }

        function filterWorkEntries() {
            const customerId = customerSelect.value;
            const propertyId = propertySelect.value;
            let visibleCount = 0;

            workInputs.forEach(function (input) {
                const matchesCustomer = Boolean(customerId)
                    && input.dataset.customerId === customerId;
                const matchesProperty = !propertyId
                    || input.dataset.propertyId === propertyId;
                const visible = matchesCustomer && matchesProperty;
                const wrapper = input.closest('div') || input.closest('label');

                if (!visible) input.checked = false;
                input.disabled = !visible;
                if (wrapper) wrapper.hidden = !visible;
                if (visible) visibleCount += 1;
            });

            if (emptyMessage) emptyMessage.hidden = visibleCount !== 0;
        }

        function refreshForCustomer() {
            replacePropertyOptions();
            filterWorkEntries();
        }

        customerSelect.addEventListener('change', refreshForCustomer);
        propertySelect.addEventListener('change', filterWorkEntries);
        refreshForCustomer();
    });
}());
