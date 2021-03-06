import _ from 'underscore';

/*
Quick shim to take an SVG text element, and rewrap its text
into tspans, using the element's text-anchor attribute
(default: 'start', or align left). Any non-text elements
(e.g. nested tspan elements) not produced by this function
are treated as single words (i.e. no attempt is made to split
nested elements across lines).
*/

function newTspan(textElement) {
    let newTspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    newTspan.setAttribute('class', 'rewrappedTspan');
    textElement.appendChild(newTspan);
    return newTspan;
}

function extractWords(element) {
    let words = [];
    // Pull out all the childNodes and split them into words
    _.each(Array.from(element.childNodes), function (chunk) {
        if (chunk.nodeType === Node.TEXT_NODE) {
            // This is an actual text node; split into real words
            _.each(chunk.textContent.split(/\s+/), function (word) {
                if (word.length > 0) {
                    words.push(new Text(word));
                }
            });
        } else if (chunk.getAttribute('class') === 'rewrappedTspan') {
            // This is a tspan that we added before; we want to flatten
            // its contents back down into the main words array
            words = words.concat(extractWords(chunk));
        } else {
            // Some other element was encountered; push it as a single "word"
            words.push(chunk);
        }
    });
    return words;
}

function rewrapSvgText(textElement, pxWidth, emLeading) {
    emLeading = emLeading || 1.1;

    let textAnchor = textElement.getAttribute('text-anchor') || 'start';
    let words = extractWords(textElement);
    if (words.length === 0) {
        return;
    }
    textElement.textContent = '';

    let lineLengths = [0];

    // First pass: figure out which words go on which lines

    // Start with the first word
    let currentTspan = newTspan(textElement);
    currentTspan.appendChild(words[0]);

    _.each(words, function (word, index) {
        // Make a temporary copy of the line
        let tempCopy = currentTspan.cloneNode(true);

        // Add a space if it's not the first word
        if (index > 0) {
            currentTspan.appendChild(new Text(' '));
        }
        // Add the word to the tspan
        currentTspan.appendChild(word);

        // How wide is the line now?
        let length = currentTspan.getComputedTextLength();

        // Has it exceeded the space that we allow?
        if (length > pxWidth && index > 0) {
            // Revert to the text we had before
            textElement.removeChild(currentTspan);
            textElement.appendChild(tempCopy);

            // Add the word to a new line
            currentTspan = newTspan(textElement);
            currentTspan.appendChild(word);
            // Store the single word's length
            lineLengths.push(currentTspan.getComputedTextLength());
        } else {
            // Update the length of this line
            lineLengths[lineLengths.length - 1] = length;
        }
    });

    // Second pass: line up each row appropriately
    _.each(Array.from(textElement.childNodes), function (tspan, index) {
        if (index === 0) {
            // Don't move the first line anywhere
            tspan.setAttribute('dx', '0px');
            tspan.setAttribute('dy', '0em');
        } else {
            tspan.setAttribute('dy', emLeading + 'em');
            let dx = 0;
            if (textAnchor === 'start') {
                // scoot the line back the
                // length of the previous line
                dx = -lineLengths[index - 1];
            } else if (textAnchor === 'middle') {
                // scoot the line back half the
                // length of the previous line,
                // as well as half the length of
                // the current line
                dx = -(lineLengths[index - 1] +
                    lineLengths[index]) / 2;
            } else { // textAnchor === 'end'
                // scoot the line back the length
                // of the current line
                dx = -lineLengths[index];
            }
            tspan.setAttribute('dx', dx + 'px');
        }
    });
}

export default rewrapSvgText;
